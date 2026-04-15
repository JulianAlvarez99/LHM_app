param (
    [Parameter(Mandatory=$true)]
    [string]$EnvPath,

    [Parameter(Mandatory=$true)]
    [string]$ClientName
)

$PrefixClientName = "recursos_$ClientName"

if (Test-Path $EnvPath) {
    $lines = Get-Content $EnvPath
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^CLIENT_TABLE_NAME=') {
            $lines[$i] = "CLIENT_TABLE_NAME=$PrefixClientName"
            $found = $true
            break
        }
    }
    if (-not $found) {
        $lines += "CLIENT_TABLE_NAME=$PrefixClientName"
    }
    Set-Content -Path $EnvPath -Value $lines -Encoding UTF8
} else {
    "CLIENT_TABLE_NAME=$PrefixClientName" | Out-File -FilePath $EnvPath -Encoding UTF8
}
