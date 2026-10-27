# Deploying the local LLM on Raspberry Pi 5

sudo apt update && sudo apt full-upgrade -y
curl -fsSL https://ollama.com/install.sh | sh        # ARM64 supported
ollama pull llama3.2:3b                              # or llama3.2:1b if replies feel slow
ollama run llama3.2:3b "hi"                          # sanity check, then /bye

## No internet on the Pi? Copy the model from your laptop
# Laptop (model already pulled):  copy the folder ~/.ollama/models  (Windows: C:\Users\<you>\.ollama\models)
# to the Pi's ~/.ollama/models   (scp -r, or a USB stick). Ollama reads it as-is.

## Keep the model loaded + start EchoMind on boot
sudo systemctl edit ollama      # add under [Service]:  Environment="OLLAMA_KEEP_ALIVE=24h"
sudo systemctl restart ollama
