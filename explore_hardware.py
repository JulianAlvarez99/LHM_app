"""
explore_hardware.py — Explorador de hardware con LibreHardwareMonitor

Ejecutar con privilegios de administrador:
    python explore_hardware.py

Genera:
  1. Reporte en consola con todo el árbol de hardware/sensores
  2. hardware_report.json  — Datos estructurados para análisis
  3. hardware_report_sql.txt — INSERT INTO listos para copiar a init_master_tables.py

IMPORTANTE: Debe ejecutarse desde el directorio donde está LibreHardwareMonitorLib.dll
"""

import os
import sys
import json
import clr
from datetime import datetime
from collections import defaultdict

# ─── Configuración .NET ────────────────────────────────────────────────────────
os.chdir(os.path.dirname(os.path.abspath(__file__)))
dll_path = os.path.join(os.getcwd(), 'LibreHardwareMonitorLib.dll')

if not os.path.exists(dll_path):
    print(f"❌ ERROR: No se encontró LibreHardwareMonitorLib.dll en:\n   {dll_path}")
    sys.exit(1)

clr.AddReference(dll_path)
from LibreHardwareMonitor.Hardware import Computer

# ─── Mapeo de tipos de hardware LHM → tipos legibles ──────────────────────────
LHM_HW_TYPE_MAP = {
    "Cpu": "CPU",
    "GpuNvidia": "GPU (NVIDIA)",
    "GpuAti": "GPU (AMD/ATI)",
    "GpuIntel": "GPU (Intel)",
    "Motherboard": "MOTHERBOARD",
    "SuperIO": "SUPER I/O (chip de la motherboard)",
    "Memory": "MEMORIA RAM",
    "Storage": "ALMACENAMIENTO",
    "Network": "RED",
    "Cooler": "COOLER",
    "EmbeddedController": "CONTROLADOR EMBEBIDO",
    "Psu": "FUENTE DE ALIMENTACIÓN",
    "Battery": "BATERÍA",
}

# Mapeo a los tipos que usás en tu BD (tabla Componente)
LHM_TO_DB_HW = {
    "Cpu": "CPU",
    "GpuNvidia": "GPU",
    "GpuAti": "GPU",
    "GpuIntel": "GPU",
    "Motherboard": "MOTHERBOARD",
    "SuperIO": "MOTHERBOARD",
    "Memory": "MEMORIA RAM",
    "Storage": "ALMACENAMIENTO",
    "Psu": "FUENTE",
}


def init_computer():
    """Inicializa LHM con todos los tipos de hardware habilitados."""
    print("🔄 Inicializando LibreHardwareMonitor...")
    c = Computer()
    c.IsCpuEnabled = True
    c.IsGpuEnabled = True
    c.IsMemoryEnabled = True
    c.IsMotherboardEnabled = True
    c.IsControllerEnabled = True
    c.IsStorageEnabled = True
    c.IsPsuEnabled = True
    c.IsNetworkEnabled = True
    c.IsBatteryEnabled = True
    c.Open()
    print("✅ LibreHardwareMonitor inicializado correctamente.\n")
    return c


def collect_hardware_tree(pc):
    """
    Recorre todo el árbol de hardware (incluyendo sub-hardware) de forma iterativa.
    Devuelve una lista de diccionarios con toda la información.
    """
    results = []
    # stack: (hw_object, depth, parent_name)
    stack = [(hw, 0, None) for hw in pc.Hardware]

    while stack:
        hw, depth, parent = stack.pop()
        hw.Update()  # Actualizar para obtener valores de sensores

        lhm_type = str(hw.HardwareType)
        hw_name = str(hw.Name)
        hw_identifier = str(hw.Identifier) if hw.Identifier else "N/A"
        db_type = LHM_TO_DB_HW.get(lhm_type, "NO MAPEADO")
        readable_type = LHM_HW_TYPE_MAP.get(lhm_type, lhm_type)

        # Recopilar sensores de este hardware
        sensors = []
        for s in hw.Sensors:
            val = float(s.Value) if s.Value is not None else None
            sensors.append({
                "sensor_name": str(s.Name),
                "sensor_type": str(s.SensorType),
                "value": val,
                "identifier": str(s.Identifier) if s.Identifier else "N/A",
                "min": float(s.Min) if s.Min is not None else None,
                "max": float(s.Max) if s.Max is not None else None,
            })

        results.append({
            "depth": depth,
            "hardware_name": hw_name,
            "hardware_type_lhm": lhm_type,
            "hardware_type_readable": readable_type,
            "hardware_type_db": db_type,
            "identifier": hw_identifier,
            "parent": parent,
            "sensors": sensors,
        })

        # Agregar sub-hardware al stack
        for sub in hw.SubHardware:
            stack.append((sub, depth + 1, hw_name))

    return results


def print_report(hardware_list):
    """Imprime un reporte formateado en consola."""
    separator = "=" * 100
    thin_sep = "-" * 100

    print(separator)
    print(f"  📊 REPORTE COMPLETO DE HARDWARE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(separator)

    total_sensors = 0
    sensor_types_seen = defaultdict(int)

    for hw in hardware_list:
        indent = "  " * hw["depth"]
        prefix = "└─ " if hw["depth"] > 0 else "■ "

        print(f"\n{indent}{prefix}🖥️  {hw['hardware_name']}")
        print(f"{indent}   Tipo LHM:        {hw['hardware_type_lhm']}")
        print(f"{indent}   Tipo legible:     {hw['hardware_type_readable']}")
        print(f"{indent}   Tipo BD (mapeo):  {hw['hardware_type_db']}")
        print(f"{indent}   Identificador:    {hw['identifier']}")
        if hw["parent"]:
            print(f"{indent}   Padre:            {hw['parent']}")

        if hw["sensors"]:
            print(f"{indent}   Sensores ({len(hw['sensors'])}):")
            print(f"{indent}   {'Nombre':<35} {'Tipo':<15} {'Valor':<15} {'Min':<12} {'Max':<12}")
            print(f"{indent}   {thin_sep[:89]}")

            for s in sorted(hw["sensors"], key=lambda x: (x["sensor_type"], x["sensor_name"])):
                val_str = f"{s['value']:.2f}" if s["value"] is not None else "N/A"
                min_str = f"{s['min']:.2f}" if s["min"] is not None else "N/A"
                max_str = f"{s['max']:.2f}" if s["max"] is not None else "N/A"
                print(f"{indent}   {s['sensor_name']:<35} {s['sensor_type']:<15} {val_str:<15} {min_str:<12} {max_str:<12}")

                total_sensors += 1
                sensor_types_seen[s["sensor_type"]] += 1
        else:
            print(f"{indent}   (Sin sensores directos)")

    # Resumen
    print(f"\n{separator}")
    print(f"  📈 RESUMEN")
    print(f"{separator}")
    print(f"  Hardware detectado:  {len(hardware_list)} componentes/sub-componentes")
    print(f"  Sensores totales:    {total_sensors}")
    print(f"\n  Distribución por tipo de sensor:")
    for stype, count in sorted(sensor_types_seen.items()):
        print(f"    • {stype:<20} → {count} sensores")
    print(separator)

    return total_sensors


def generate_sql_inserts(hardware_list):
    """
    Genera las líneas INSERT listas para copiar a init_master_tables.py.
    Usa pares únicos (sensor_name, sensor_type).
    """
    unique_sensors = {}  # (name, type) → first value seen
    for hw in hardware_list:
        for s in hw["sensors"]:
            key = (s["sensor_name"], s["sensor_type"])
            if key not in unique_sensors:
                unique_sensors[key] = s["value"]

    lines = []
    lines.append("# ─── Sensores detectados en esta máquina ───────────────────────")
    lines.append("# Copiar al array 'sensores' de init_master_tables.py")
    lines.append("# Ajustar los sensor_id según la numeración que ya tengas en la BD")
    lines.append("sensores_detectados = [")

    for i, ((name, stype), val) in enumerate(sorted(unique_sensors.items(), key=lambda x: (x[0][1], x[0][0])), start=1):
        val_str = f"{val:.2f}" if val is not None else "N/A"
        lines.append(f'    ({i}, "{name}", "{stype}"),  # valor actual: {val_str}')

    lines.append("]")
    lines.append(f"\n# Total: {len(unique_sensors)} sensores únicos detectados")

    return "\n".join(lines), unique_sensors


def generate_comparison(hardware_list, unique_sensors):
    """
    Genera una comparación entre los sensores detectados y los que tenés
    hardcodeados en init_master_tables.py para identificar los faltantes.
    """
    # Sensores actuales en init_master_tables.py (hardcodeados)
    existing_sensors = {
        ("Memory", "Load"), ("Virtual Memory", "Load"),
        ("Temperature", "Temperature"), ("Used Space", "Load"),
        ("Read Activity", "Load"), ("Write Activity", "Load"),
        ("Total Activity", "Load"), ("Life", "Level"),
        ("GPU Package", "Power"), ("GPU Core", "Temperature"),
        ("GPU Memory Junction", "Temperature"),
        ("Vcore", "Voltage"), ("+12V", "Voltage"),
        ("+5V", "Voltage"), ("+3.3V", "Voltage"),
        ("VRM MOS", "Temperature"), ("CPU Fan", "Fan"),
        ("Core (Tctl/Tdie)", "Temperature"), ("Package", "Power"),
        ("CPU Total", "Load"), ("GPU Core", "Load"),
    }

    # Agregar System Fan y CPU Core patterns
    for i in range(1, 17):
        existing_sensors.add((f"CPU Core #{i}", "Load"))
    for i in range(1, 7):
        existing_sensors.add((f"System Fan #{i}", "Fan"))
        existing_sensors.add((f"System Fan #{i} / Pump", "Fan"))

    detected = set(unique_sensors.keys())
    missing = detected - existing_sensors
    extra = existing_sensors - detected

    lines = []
    lines.append("\n" + "=" * 100)
    lines.append("  🔍 COMPARACIÓN: Sensores detectados vs. init_master_tables.py")
    lines.append("=" * 100)

    if missing:
        lines.append(f"\n  ⚠️  SENSORES NUEVOS (detectados pero NO están en init_master_tables.py): {len(missing)}")
        lines.append(f"  {'Nombre':<40} {'Tipo':<15} {'Valor actual':<15}")
        lines.append(f"  {'-'*70}")
        for name, stype in sorted(missing, key=lambda x: (x[1], x[0])):
            val = unique_sensors[(name, stype)]
            val_str = f"{val:.2f}" if val is not None else "N/A"
            lines.append(f"  {name:<40} {stype:<15} {val_str:<15}")
    else:
        lines.append("\n  ✅ Todos los sensores detectados ya están en init_master_tables.py")

    if extra:
        lines.append(f"\n  ℹ️  Sensores en init_master_tables.py que NO se detectaron en este hardware: {len(extra)}")
        lines.append(f"  (Esto es normal si esta máquina tiene hardware diferente)")
        for name, stype in sorted(extra, key=lambda x: (x[1], x[0])):
            lines.append(f"    • {name} ({stype})")

    lines.append("=" * 100)
    return "\n".join(lines)


def save_json_report(hardware_list, filepath):
    """Guarda el reporte completo en formato JSON."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "machine_info": {
            "total_hardware": len(hardware_list),
            "total_sensors": sum(len(hw["sensors"]) for hw in hardware_list),
        },
        "hardware": hardware_list,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"📄 Reporte JSON guardado en: {filepath}")


def main():
    pc = init_computer()

    try:
        # 1. Recopilar todo el árbol de hardware
        hardware_list = collect_hardware_tree(pc)

        # 2. Imprimir reporte en consola
        total = print_report(hardware_list)

        # 3. Generar fragmento SQL
        sql_text, unique_sensors = generate_sql_inserts(hardware_list)

        # 4. Comparar con lo que ya tenés
        comparison = generate_comparison(hardware_list, unique_sensors)
        print(comparison)

        # 5. Guardar archivos
        base_dir = os.path.dirname(os.path.abspath(__file__))

        # JSON completo
        json_path = os.path.join(base_dir, "hardware_report.json")
        save_json_report(hardware_list, json_path)

        # SQL inserts
        sql_path = os.path.join(base_dir, "hardware_report_sql.txt")
        with open(sql_path, "w", encoding="utf-8") as f:
            f.write(sql_text)
        print(f"📄 Fragmento SQL guardado en: {sql_path}")

        # Reporte de texto completo (para referencia)
        txt_path = os.path.join(base_dir, "hardware_report_full.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            # Redirigir el print_report a archivo también
            import io
            buf = io.StringIO()

            # Header
            buf.write(f"REPORTE COMPLETO DE HARDWARE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            buf.write("=" * 100 + "\n")

            for hw in hardware_list:
                indent = "  " * hw["depth"]
                prefix = "└─ " if hw["depth"] > 0 else "■ "
                buf.write(f"\n{indent}{prefix}{hw['hardware_name']}\n")
                buf.write(f"{indent}   Tipo LHM: {hw['hardware_type_lhm']}  |  Tipo BD: {hw['hardware_type_db']}  |  ID: {hw['identifier']}\n")
                if hw["parent"]:
                    buf.write(f"{indent}   Padre: {hw['parent']}\n")
                if hw["sensors"]:
                    buf.write(f"{indent}   Sensores ({len(hw['sensors'])}):\n")
                    for s in sorted(hw["sensors"], key=lambda x: (x["sensor_type"], x["sensor_name"])):
                        val_str = f"{s['value']:.2f}" if s["value"] is not None else "N/A"
                        buf.write(f"{indent}     - {s['sensor_name']} [{s['sensor_type']}] = {val_str}\n")

            buf.write(f"\n{'=' * 100}\n")
            buf.write(f"Total: {len(hardware_list)} componentes, {total} sensores\n")
            buf.write(f"\n{comparison}\n")
            buf.write(f"\n{sql_text}\n")

            f.write(buf.getvalue())
        print(f"📄 Reporte completo guardado en: {txt_path}")

        print(f"\n✅ Exploración completada. {len(hardware_list)} componentes, {total} sensores detectados.")
        print("   Revisá los archivos generados para ver qué sensores agregar a tu BD.")

    finally:
        pc.Close()
        print("🔒 LibreHardwareMonitor cerrado.")


if __name__ == "__main__":
    main()
