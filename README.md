# Monitor de Concursos Públicos — UNICAMP

Monitora automaticamente a página de inscrições abertas da UNICAMP e envia um **e-mail de notificação** sempre que detectar qualquer mudança no conteúdo.

> **Página monitorada:** https://www.siarh.unicamp.br/concurso/InscricoesAbertas.jsf

---

## Pré-requisitos

- Python 3.8 ou superior
- Acesso a uma conta de e-mail com SMTP (Gmail, Outlook, etc.)
- Conexão com a internet

---

## Instalação

### 1. Clone ou baixe o projeto

```bash
cd /caminho/onde/quiser
git clone <url-do-repositorio>
cd projetoVisualizacaoDGRH
```

### 2. Crie o ambiente virtual Python

```bash
python3 -m venv .venv
```

> **Ubuntu/Debian:** se der erro, instale o pacote necessário primeiro:
> ```bash
> sudo apt install python3-venv
> ```

### 3. Ative o ambiente virtual

```bash
# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 4. Instale as dependências

```bash
pip install -r requirements.txt
```

---

## Configuração do E-mail

### 1. Copie o arquivo de exemplo

```bash
cp .env.example .env
```

### 2. Edite o arquivo `.env` com seus dados

```
EMAIL_FROM=seu_email@gmail.com
EMAIL_PASSWORD=sua_senha_de_app
EMAIL_TO=destinatario@example.com
CHECK_INTERVAL_MINUTES=60
```

### Usando Gmail (recomendado)

O Gmail exige uma **Senha de App** (diferente da sua senha normal), especialmente se você tiver a verificação em duas etapas ativada.

**Como gerar a Senha de App:**

1. Acesse https://myaccount.google.com/apppasswords
2. Faça login na sua conta Google
3. Em "Selecionar app", escolha **"Outro (nome personalizado)"**
4. Digite um nome (ex.: `Monitor UNICAMP`) e clique em **Gerar**
5. Copie a senha gerada (16 caracteres) e cole no campo `EMAIL_PASSWORD` do seu `.env`

> **Atenção:** a verificação em duas etapas precisa estar ativada na conta para usar Senhas de App.

### Usando múltiplos destinatários

Separe os e-mails com vírgula no campo `EMAIL_TO`:

```
EMAIL_TO=voce@gmail.com,colega@outlook.com
```

---

## Como Rodar

### Opção A — Loop contínuo (processo rodando em segundo plano)

Verifica a página a cada 60 minutos (ou o intervalo configurado no `.env`):

```bash
source .venv/bin/activate
python monitor.py
```

Para definir um intervalo diferente (ex.: a cada 30 minutos):

```bash
python monitor.py --interval 30
```

Encerre com `Ctrl+C`.

---

### Opção B — Agendamento via cron (recomendado para servidores)

Rode uma única verificação por execução e deixe o cron controlar o horário.

**Edite o crontab:**

```bash
crontab -e
```

**Adicione uma linha ao final** (exemplo: verificar a cada hora):

```
0 * * * * /caminho/completo/projetoVisualizacaoDGRH/.venv/bin/python /caminho/completo/projetoVisualizacaoDGRH/monitor.py --run-once
```

> Substitua `/caminho/completo/` pelo caminho real do projeto. Use `pwd` dentro da pasta do projeto para descobrir.

**Exemplo com o caminho real:**

```
0 * * * * /home/gpereira/Desktop/development/projetoVisualizacaoDGRH/.venv/bin/python /home/gpereira/Desktop/development/projetoVisualizacaoDGRH/monitor.py --run-once
```

---

### Opção C — Serviço systemd (para rodar automaticamente no boot)

Crie o arquivo de serviço:

```bash
sudo nano /etc/systemd/system/monitor-unicamp.service
```

Conteúdo do arquivo:

```ini
[Unit]
Description=Monitor de Concursos UNICAMP
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=gpereira
WorkingDirectory=/home/gpereira/Desktop/development/projetoVisualizacaoDGRH
ExecStart=/home/gpereira/Desktop/development/projetoVisualizacaoDGRH/.venv/bin/python monitor.py
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
```

Ative e inicie o serviço:

```bash
sudo systemctl daemon-reload
sudo systemctl enable monitor-unicamp
sudo systemctl start monitor-unicamp

# Verificar status:
sudo systemctl status monitor-unicamp

# Ver logs em tempo real:
journalctl -u monitor-unicamp -f
```

---

### Opção D — GitHub Actions (roda na nuvem, sem ligar o computador)

O projeto também pode rodar automaticamente pelo GitHub Actions. Nesse modo, o GitHub executa o script em horários definidos, mesmo com seu computador desligado.

O arquivo de workflow está em:

```text
.github/workflows/monitor.yml
```

Por padrão, ele roda duas vezes por dia, às 09:00 e 15:00 no horário de São Paulo, e também permite execução manual pela aba **Actions** do GitHub.

#### 1. Suba o projeto para um repositório no GitHub

Garanta que o arquivo `.env` não seja enviado para o GitHub. Ele já está listado no `.gitignore`.

#### 2. Cadastre os Secrets no GitHub

No repositório, acesse:

```text
Settings > Secrets and variables > Actions > New repository secret
```

Cadastre:

```text
EMAIL_FROM
EMAIL_PASSWORD
EMAIL_TO
SMTP_HOST
SMTP_PORT
```

Para Gmail, normalmente:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
```

#### 3. Teste manualmente

No GitHub, vá em:

```text
Actions > Monitor UNICAMP > Run workflow
```

Para testar o monitor normal, escolha o modo `monitor`. Na primeira execução, o script salva o estado inicial. Ele só envia e-mail quando detectar mudança em uma execução posterior.

Para testar o envio de e-mail, escolha o modo `test-email`. Esse modo envia um e-mail de teste usando as configurações cadastradas nos Secrets.

> Observação: o GitHub Actions usa horários em UTC. O agendamento `0 12,18 * * *` equivale a 09:00 e 15:00 no horário de São Paulo.

---

## Testar as Configurações de E-mail

Antes de deixar o monitor rodando, teste se o e-mail está funcionando:

```bash
source .venv/bin/activate
python monitor.py --test-email
```

Se tudo estiver correto, você receberá um e-mail de teste no endereço configurado em `EMAIL_TO`.

---

## Arquivos Gerados

| Arquivo | Descrição |
|---|---|
| `state.json` | Guarda o último conteúdo capturado para comparação. Criado automaticamente na primeira execução. |
| `monitor.log` | Log de todas as verificações realizadas. |

---

## Como Funciona

1. O script acessa a página da UNICAMP e extrai o conteúdo da seção de inscrições abertas.
2. Remove o timestamp dinâmico da página (para evitar falsos positivos).
3. Calcula um hash SHA-256 do conteúdo.
4. Compara com o hash da última verificação salvo em `state.json`.
5. Se o hash for diferente, **envia um e-mail** mostrando o conteúdo anterior e o novo.
6. Atualiza o estado salvo.

---

## Solução de Problemas

**"Falha de autenticação SMTP"**
→ Para Gmail, certifique-se de usar uma **Senha de App**, não a senha normal da conta.

**"Variáveis de e-mail não configuradas"**
→ Verifique se o arquivo `.env` existe e tem os campos `EMAIL_FROM`, `EMAIL_PASSWORD` e `EMAIL_TO` preenchidos.

**Recebendo notificações a cada verificação sem mudança real**
→ Delete o arquivo `state.json` e deixe o monitor reconstruir o estado inicial.

**Verificar os logs:**
```bash
tail -f monitor.log
```
