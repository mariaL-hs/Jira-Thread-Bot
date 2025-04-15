# Jira Automation Bot

Um bot de automação entre o Jira e o Discord, que cria threads no Discord automaticamente quando tarefas são movidas para o status "Em Andamento".

## Características

- Criação automática de threads no Discord para tarefas em andamento no Jira
- Atualização automática de títulos das threads quando o título da tarefa muda no Jira
- Mapeamento de usuários entre Jira e Discord 
- Menção automática do responsável pela tarefa no Discord com base no mapemeamento
- Slash Commands para gerenciamento do bot
- Mapeamento em arquivos JSON


## Configuração
### Pré-requisitos

- Python 3.8 ou superior
- Conta no Discord com permissões para criar um bot
- Todas as permissões Intents do bot ativadas
- Acesso administrativo ao Jira para configurar webhooks

### Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:
- DISCORD_BOT_TOKEN=seu_token_do_discord_aqui
- JIRA_WEBHOOK_URL=url_do_seu_webhook_jira

### Instalação

1. Clone o repositório:
    ```bash
    git clone (https://github.com/mariaL-hs/thread-bot.git)
    ````
2. Instale as dependências:
    ```bash
    pip install -r requirements.txt
   ````
3. Execute o bot:
    ```bash
    py bot.py
   ````
## Arquivos do Projeto

- bot.py: Arquivo principal do projeto que contém toda a lógica do bot e da API
- Procfile: Configuração para deploy em serviços como Heroku/Railway
- requirements.txt: Lista de dependências Python
- user_mapping.json: Armazena o mapeamento entre usuários do Jira e Discord
- task_thread_map.json: Armazena o mapeamento entre tarefas do Jira e threads do Discord para evitar criação duplicada de thread
- .env: Armazena variáveis de ambiente (não versionado)
- .gitignore: Lista de arquivos ignorados pelo Git (.env)

## Comandos do Discord
O bot oferece os seguintes comandos slash (use "/"):

- /ativar - Ativa o bot no canal atual
- /desativar - Desativa o bot no canal atual
- /mapear_usuario [jira_user] [discord_user] - Mapeia um usuário do Jira para um usuário do Discord
- /listar_mapeamentos - Lista todos os mapeamentos de usuários
- /remover_mapeamento [jira_user] - Remove um mapeamento de usuário

## Configuração do Webhook no Jira

1. No Jira: Configurações > Sistema > Webhooks
2. Adicione um novo webhook com a URL "http://seu-servidor:5000/jira-webhook"
3. Configure o webhook para disparar em eventos de:
- JQL: project = TASK AND type in (Bug, Task) AND status = "Em andamento" ORDER BY created DESC
- Item: atualizado
- Log de trabalho: atualizado
- Filtro: atualizado

### Deployment
Para deploy em servidores como Heroku ou Railway, o Procfile já está configurado. 

## Troubleshooting
### Se o bot não responder aos comandos:

- Verifique se o bot está online na lista de membros do discord e ativado no canal correto
- Confira se o token do Discord está correto no arquivo .env
- Confirme se as permissões "Intents" nas configurações do bot estão ativadas

### Se as threads não forem criadas quando tarefas mudarem de status:

- Verifique se o webhook do Jira está configurado corretamente
- Tenha certeza de que o bot tem as permissões necessárias tanto no código, quanto nas configurações do discord dev
