import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE ZONA HORARIA
# Modificá este valor si el servidor o los clientes cambian de región.
# También se puede definir DB_TIMEZONE en el .env para sobreescribirlo.
# Valores comunes:
#   'America/Argentina/Buenos_Aires'  → UTC-3  (Argentina)
#   'America/Santiago'                → UTC-3/-4 (Chile, con horario de verano)
#   'America/Sao_Paulo'               → UTC-3  (Brasil)
#   'UTC'                             → Sin conversión
# Lista completa en PostgreSQL: SELECT name FROM pg_timezone_names;
TIMEZONE = os.getenv("DB_TIMEZONE", "America/Argentina/Buenos_Aires")

# Segundos extra que un evento debe seguir abierto antes de avisarse.
# Filtra los cortes de ingesta que el cliente rellena con su buffer (queue de
# capture.py) sin perder un solo dato. Tiempo total hasta avisar = 60s + este valor.
CONFIRMACION_SEGUNDOS = int(os.getenv("CONFIRMACION_DESCONEXION", 30))

# Silencio necesario para abrir el evento (provisional, todavía sin avisar).
# No bajar cerca de UPDATE_TIME de capture.py: el jitter normal de un ciclo de
# captura abriría eventos sin parar. Piso sano ≈ 3x UPDATE_TIME.
SILENCIO_SEGUNDOS = int(os.getenv("SILENCIO_DESCONEXION", 30))

# Cada cuánto corre el detector. Es la granularidad: sumá hasta este valor al
# tiempo total de aviso. Cada corrida hace un MAX(timestamp) por tabla de cliente.
JOB_SEGUNDOS = int(os.getenv("INTERVALO_DETECCION", 20))
# ─────────────────────────────────────────────────────────────────────────────

def implement_monitoring_logic():
    conn = None
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            database=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASS", os.getenv("DB_PASSWORD", "")),
            port=os.getenv("DB_PORT", "5432")
        )
        cur = conn.cursor()

        # ── 1. OBTENER TABLAS DE CLIENTES ─────────────────────────────────────
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name LIKE 'recursos_%'
              AND table_schema = 'public';
        """)
        tablas_clientes = [row[0] for row in cur.fetchall()]

        if not tablas_clientes:
            print("No se encontraron tablas con el prefijo 'recursos_'.")
            return

        # ── 2. FUNCIÓN: AUDITAR UMBRALES ──────────────────────────────────────
        # FIX: Usamos TG_TABLE_NAME en lugar de TG_RELID::regclass::text.
        #
        # TG_TABLE_NAME es una variable especial de PL/pgSQL que contiene
        # el nombre de la tabla que disparó el trigger. Para hypertables de
        # TimescaleDB, cuando el trigger se define sobre la tabla padre
        # (recursos_xxx), TG_TABLE_NAME devuelve 'recursos_xxx' correctamente,
        # incluso aunque internamente TimescaleDB lo ejecute sobre un chunk.
        cur.execute(f"""
            CREATE OR REPLACE FUNCTION fn_auditar_umbrales()
            RETURNS TRIGGER AS $$
            DECLARE
                v_cliente VARCHAR;
            BEGIN
                -- Resolvemos el nombre real de la tabla (si se dispara en un chunk, buscamos su padre)
                SELECT parent.relname INTO v_cliente
                FROM pg_inherits
                JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
                WHERE pg_inherits.inhrelid = TG_RELID
                LIMIT 1;

                IF v_cliente IS NULL THEN
                    v_cliente := TG_TABLE_NAME;
                END IF;

                -- Solo inserta si el valor supera el umbral definido para ese sensor.
                INSERT INTO auditoria_componente (timestamp, cliente, hardware_id, sensor_id, value)
                SELECT
                    -- Tomamos el timestamp local (naive) de capture.py y lo interpretamos 
                    -- en la zona de Argentina para obtener el TIMESTAMPTZ absoluto correcto.
                    NEW.timestamp AT TIME ZONE '{TIMEZONE}',
                    v_cliente,
                    NEW.hardware_id,
                    NEW.sensor_id,
                    NEW.value
                FROM umbrales u
                WHERE u.sensor_id = NEW.sensor_id
                  AND NEW.value > u.umbral_max;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("✅ Función fn_auditar_umbrales creada/actualizada.")

        # ── 3. FUNCIÓN: REGISTRAR RECONEXIÓN ──────────────────────────────────
        # Cuando llega un nuevo dato de un cliente que estaba desconectado,
        # se cierra el registro abierto en auditoria_clientes.
        cur.execute(f"""
            CREATE OR REPLACE FUNCTION fn_registrar_reconexion()
            RETURNS TRIGGER AS $$
            DECLARE
                v_cliente VARCHAR;
            BEGIN
                -- Resolvemos el nombre real de la tabla (si se dispara en un chunk, buscamos su padre)
                SELECT parent.relname INTO v_cliente
                FROM pg_inherits
                JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
                WHERE pg_inherits.inhrelid = TG_RELID
                LIMIT 1;

                IF v_cliente IS NULL THEN
                    v_cliente := TG_TABLE_NAME;
                END IF;

                -- Evento abierto que nunca se avisó (alerta = 0): fue lag de ingesta,
                -- no una desconexión. El cliente volvió con su buffer intacto y sin
                -- perder datos. Se borra sin dejar rastro y sin disparar NOTIFY.
                DELETE FROM auditoria_clientes
                 WHERE cliente          = v_cliente
                   AND fin_desconexion IS NULL
                   AND alerta           = 0;

                -- Si queda un evento abierto (ya avisado), lo cerramos.
                UPDATE auditoria_clientes
                SET
                    fin_desconexion = NEW.timestamp AT TIME ZONE '{TIMEZONE}',
                    duracion        = (NEW.timestamp AT TIME ZONE '{TIMEZONE}') - inicio_desconexion
                WHERE cliente          = v_cliente
                  AND fin_desconexion IS NULL;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("✅ Función fn_registrar_reconexion creada/actualizada.")

        # ── 4. ASOCIAR TRIGGERS A CADA TABLA DE CLIENTE ───────────────────────
        for tabla in tablas_clientes:
            # Trigger AFTER INSERT → audita umbrales con el nuevo dato ya confirmado
            cur.execute(f"DROP TRIGGER IF EXISTS tr_verificar_umbrales ON {tabla};")
            cur.execute(f"""
                CREATE TRIGGER tr_verificar_umbrales
                AFTER INSERT ON {tabla}
                FOR EACH ROW EXECUTE FUNCTION fn_auditar_umbrales();
            """)

            # Trigger BEFORE INSERT → cierra eventos de desconexión abiertos
            # Se ejecuta ANTES para que fin_desconexion quede con la marca exacta
            # del primer dato que vuelve, no después de procesarlo.
            cur.execute(f"DROP TRIGGER IF EXISTS tr_reconexion ON {tabla};")
            cur.execute(f"""
                CREATE TRIGGER tr_reconexion
                BEFORE INSERT ON {tabla}
                FOR EACH ROW EXECUTE FUNCTION fn_registrar_reconexion();
            """)
            print(f"   ↳ Triggers sincronizados en: {tabla}")

        # ── 5. PROCEDIMIENTO: DETECTAR DESCONEXIONES ─────────────────────────
        # Este procedure lo ejecuta el scheduler de TimescaleDB cada N segundos.
        # Su única responsabilidad es detectar clientes "en silencio" (sin datos
        # nuevos en la ventana temporal) y abrir un evento en auditoria_clientes.
        #
        # FIX TIMEZONE:
        # capture.py inserta con datetime.now() → timestamp naive que el VPS
        # (UTC) almacena tal cual. Casteamos a TIMESTAMPTZ y convertimos a
        # 'America/Argentina/Buenos_Aires' (UTC-3 fijo). NOW() también se
        # convierte a la misma zona antes de comparar, así la ventana de
        # silencio es siempre relativa a la hora local argentina.
        cur.execute(f"""
            CREATE OR REPLACE PROCEDURE proc_detectar_desconexion(job_id int, config jsonb)
            LANGUAGE plpgsql AS $$
            DECLARE
                r                  RECORD;
                v_tz               TEXT      := '{TIMEZONE}';
                v_ventana_silencio INTERVAL  := '{SILENCIO_SEGUNDOS} seconds';
                v_confirmacion     INTERVAL  := '{CONFIRMACION_SEGUNDOS} seconds';
                v_ultimo_dato      TIMESTAMPTZ;
                v_ahora            TIMESTAMPTZ;
                v_ya_registrado    BOOLEAN;
            BEGIN
                -- Hora actual absoluta del servidor, para comparar contra las marcas de tiempo.
                v_ahora := NOW();

                FOR r IN (
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_name LIKE 'recursos_%'
                      AND table_schema = 'public'
                ) LOOP
                    BEGIN
                        -- Leemos el último timestamp (naive en local) de la tabla del cliente 
                        -- y lo interpretamos en la zona definida para obtener el TIMESTAMPTZ absoluto.
                        EXECUTE format(
                            'SELECT MAX(timestamp) AT TIME ZONE %L FROM %I',
                            v_tz, r.table_name
                        ) INTO v_ultimo_dato;

                        -- Si la tabla está vacía o el último dato es reciente, saltamos.
                        IF v_ultimo_dato IS NULL OR v_ultimo_dato > v_ahora - v_ventana_silencio THEN
                            CONTINUE;
                        END IF;

                        -- Verificamos si ya existe un evento de desconexión abierto.
                        SELECT EXISTS (
                            SELECT 1
                            FROM auditoria_clientes
                            WHERE cliente = r.table_name
                              AND fin_desconexion IS NULL
                        ) INTO v_ya_registrado;

                        -- Solo abrimos un evento nuevo si no hay uno ya abierto.
                        IF NOT v_ya_registrado THEN
                            INSERT INTO auditoria_clientes (inicio_desconexion, cliente)
                            VALUES (v_ultimo_dato, r.table_name);

                            RAISE NOTICE 'Desconexión detectada para %: último dato en % (hora ARG)',
                                r.table_name, v_ultimo_dato;
                        END IF;

                    EXCEPTION WHEN OTHERS THEN
                        RAISE NOTICE 'Error procesando tabla %: %', r.table_name, SQLERRM;
                    END;
                END LOOP;

                -- ── CONFIRMACIÓN: avisar sólo lo que sigue caído ──────────────
                -- El evento se abre a los 60 s de silencio pero no se anuncia hasta
                -- que la ausencia de datos supera silencio + confirmación. Si el
                -- cliente reaparece antes, fn_registrar_reconexion ya lo borró.
                FOR r IN (
                    SELECT cliente, inicio_desconexion
                    FROM auditoria_clientes
                    WHERE fin_desconexion IS NULL
                      AND alerta = 0
                      AND inicio_desconexion < v_ahora - (v_ventana_silencio + v_confirmacion)
                ) LOOP
                    UPDATE auditoria_clientes
                       SET alerta = 1
                     WHERE cliente = r.cliente
                       AND inicio_desconexion = r.inicio_desconexion;

                    PERFORM pg_notify('alertas_clientes', json_build_object(
                        'cliente',            r.cliente,
                        'inicio_desconexion', r.inicio_desconexion
                    )::text);

                    RAISE NOTICE 'Desconexión confirmada y avisada para %', r.cliente;
                END LOOP;

                COMMIT;
            END;
            $$;
        """)
        print("✅ Procedure proc_detectar_desconexion creado/actualizado.")

        # ── 5b. NOTIFY DE RECONEXIÓN + LIMPIEZA DE TRIGGERS LEGADOS ──────────
        # El aviso de desconexión ahora lo emite el procedure (confirmado).
        # Acá queda sólo el de reconexión, que sí puede dispararse al instante.
        cur.execute("""
            CREATE OR REPLACE FUNCTION fn_notificar_reconexion()
            RETURNS TRIGGER AS $$
            BEGIN
                IF NEW.fin_desconexion IS NOT NULL AND OLD.fin_desconexion IS NULL THEN
                    PERFORM pg_notify('alertas_clientes', json_build_object(
                        'cliente',            NEW.cliente,
                        'inicio_desconexion', NEW.inicio_desconexion,
                        'fin_desconexion',    NEW.fin_desconexion,
                        'duracion',           NEW.duracion
                    )::text);
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)

        # Cualquier trigger viejo que notifique 'alertas_clientes' al INSERT sigue
        # avisando sin confirmar. Se localizan por el cuerpo de su función y se borran.
        cur.execute("""
            SELECT t.tgname
            FROM pg_trigger t
            JOIN pg_proc p ON p.oid = t.tgfoid
            WHERE t.tgrelid = 'auditoria_clientes'::regclass
              AND NOT t.tgisinternal
              AND p.prosrc LIKE '%alertas_clientes%'
              AND p.proname <> 'fn_notificar_reconexion';
        """)
        for (tg,) in cur.fetchall():
            cur.execute(f'DROP TRIGGER IF EXISTS "{tg}" ON auditoria_clientes;')
            print(f"   ↳ Trigger legado eliminado: {tg}")

        cur.execute("DROP TRIGGER IF EXISTS tr_notificar_reconexion ON auditoria_clientes;")
        cur.execute("""
            CREATE TRIGGER tr_notificar_reconexion
            AFTER UPDATE ON auditoria_clientes
            FOR EACH ROW EXECUTE FUNCTION fn_notificar_reconexion();
        """)
        print("✅ NOTIFY de reconexión configurado en auditoria_clientes.")

        # ── 6. REGISTRAR O MANTENER EL JOB EN EL SCHEDULER ───────────────────
        cur.execute("""
            SELECT job_id
            FROM timescaledb_information.jobs
            WHERE proc_name = 'proc_detectar_desconexion';
        """)
        job = cur.fetchone()
        intervalo = f"{JOB_SEGUNDOS} seconds"
        if job is None:
            cur.execute("SELECT add_job('proc_detectar_desconexion', %s);", (intervalo,))
            print(f"✅ Job de monitoreo (cada {JOB_SEGUNDOS}s) registrado.")
        else:
            # add_job no pisa un job existente: para cambiar la cadencia hay que alterarlo.
            cur.execute(
                "SELECT alter_job(%s, schedule_interval => %s::interval);",
                (job[0], intervalo),
            )
            print(f"✅ Job existente sincronizado a cada {JOB_SEGUNDOS}s.")

        conn.commit()
        print("\n--- PROCESO COMPLETADO EXITOSAMENTE ---")

    except Exception as e:
        print(f"Error crítico durante la implementación: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    implement_monitoring_logic()