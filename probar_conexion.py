import urllib.request
import urllib.error
import json

KEY = "AQ.Ab8RN6JjPCgRre0p0lYK8BtiKd7fSFPBjc_OjWaWkgHvdkV-pg"
URL = f"https://generativelanguage.googleapis.com/v1beta/models?key={KEY}"

print("📡 Probando conexión directa con los servidores de Google...\n")

try:
    req = urllib.request.Request(URL)
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        print("✅ ¡Conexión exitosa! Estos son los modelos habilitados para tu clave:\n")
        for m in data.get('models', []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                print(f" • {m['name'].replace('models/', '')}")
                
except urllib.error.HTTPError as e:
    print(f"❌ Error HTTP {e.code} desde Google:")
    print(e.read().decode())
except Exception as e:
    print(f"❌ Error inesperado: {e}")