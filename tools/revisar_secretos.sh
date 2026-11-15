#!/usr/bin/env bash
# revisar_secretos.sh — falla si el repositorio trae archivos de secretos/datos o cadenas que parecen claves.
# Lo ejecuta el CI en cada Pull Request; también puedes correrlo antes de hacer commit:  bash tools/revisar_secretos.sh
# Es una red de seguridad simple, no sustituye a GitHub secret scanning (activado en el repositorio) ni a tu criterio.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
fallo=0

echo "== Archivos que nunca deben estar versionados"
prohibidos=$(git ls-files | grep -E '(^|/)(\.env|wifi_config\.h|voz_config\.h|firma-privada\.pem|memoria\.db|perfil\.json)$|\.(pem|key|p12|pfx|db|sqlite|sqlite3|wav|mp3|zip|tflite|onnx)$|(^|/)datos/|(^|/)placa_real/|(^|/)reales/' | grep -v -E 'firma_publica' || true)
if [ -n "$prohibidos" ]; then echo "$prohibidos"; echo "ERROR: archivos prohibidos"; fallo=1; fi

echo "== Cadenas que parecen secretos"
patrones=(
  '-----BEGIN ([A-Z]+ )?PRIVATE KEY-----'
  'gsk_[A-Za-z0-9]{20,}'                  # Groq
  'sk-[A-Za-z0-9_-]{20,}'                 # claves tipo OpenAI/OpenCode
  'gh[pousr]_[A-Za-z0-9]{30,}'            # GitHub
  'AKIA[0-9A-Z]{16}'                      # AWS
  'xox[baprs]-[A-Za-z0-9-]{10,}'          # Slack
  '(token|clave|password|passwd|secret|api_?key)[A-Za-z_]*[[:space:]]*[:=][[:space:]]*"[A-Za-z0-9+/_=.-]{24,}"'
)
for p in "${patrones[@]}"; do
  if git grep -n -I -E -i -e "$p" -- . ':!tools/revisar_secretos.sh' ':!*.example*' ':!docs/*' ':!server/test_*.py' >/tmp/hallazgos.txt 2>/dev/null; then
    echo "Coincidencia con: $p"; cat /tmp/hallazgos.txt; fallo=1
  fi
done

echo "== Direcciones IP privadas o de servidores concretos (solo se permiten las de ejemplo)"
if git grep -n -I -E '\b(192\.168\.[0-9]+\.[0-9]+|10\.[0-9]+\.[0-9]+\.[0-9]+)\b' -- . ':!*.example*' ':!docs/*' ':!server/test_*.py' ':!firmware/pruebas_pc/*' \
   | grep -v -E '192\.168\.4\.1|192\.168\.1\.100' >/tmp/ips.txt; then
  cat /tmp/ips.txt; echo "ERROR: IPs sueltas (usa variables o un ejemplo en .example)"; fallo=1
fi

[ "$fallo" -eq 0 ] && echo "OK: sin hallazgos" || echo "FALLO: revisa lo anterior"
exit "$fallo"
