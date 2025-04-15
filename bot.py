import discord
from discord.ext import commands
from discord import app_commands
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import asyncio
import threading
import json
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
JIRA_URL = os.getenv("JIRA__URL")

if not TOKEN:
    print("DISCORD_BOT_TOKEN não encontrado. Verifique o arquivo .env")

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

active_channel = None
 
# dicionário p/ mapeamento
task_thread_map = {}


# ----- Funções de gerenciamento de arquivos JSON 

def load_json_file(filename, default=None):
    if default is None:
        default = {}
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Arquivo {filename} não encontrado. Criando um novo arquivo...")
        save_json_file(filename, default)
        return default
    except json.JSONDecodeError:
        print(f"Erro ao decodificar {filename}. Verifique o formato.")
        return default

def save_json_file(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

user_mapping = load_json_file('user_mapping.json')
task_thread_map = load_json_file('task_thread_map.json')

def save_task_thread_map():
    save_json_file('task_thread_map.json', task_thread_map)

def save_user_mapping():
    save_json_file('user_mapping.json', user_mapping)


# ----- Configuração da API FastAPI

app = FastAPI(title="Jira Discord Integration")

# modelos de dados p/ webhook do Jira
class JiraAssignee(BaseModel):
    key: str = None
    name: str = None
    displayName: str = None
    emailAddress: str = None

class JiraStatusCategory(BaseModel):
    name: str

class JiraStatus(BaseModel):
    name: str
    statusCategory: JiraStatusCategory

class JiraFields(BaseModel):
    summary: str
    status: JiraStatus
    assignee: JiraAssignee = None

class JiraIssue(BaseModel):
    key: str
    fields: JiraFields

class JiraIssueUpdate(BaseModel):
    issue: JiraIssue


# ----- Funções para gerenciamento de threads

async def get_thread_for_task(task_key):
    """
    verifica se existe uma thread para a tarefa e retorna
    se existir mas nao for encontrada ou foi deletada é removido do mapeamento
    """
    if task_key in task_thread_map:
        thread_id = int(task_thread_map[task_key])
        try:
            thread = await bot.fetch_channel(thread_id)
            return thread
        except discord.NotFound:
            del task_thread_map[task_key]
            save_task_thread_map()
    return None

async def create_or_update_thread_from_jira(task_key, task_summary, assignee=None):
    """
        task_key: codigo da task (TASK-000)
        task_summary: titulo da tarefa
        assignee: objeto contendo informaçoes do responsavel
    """
    if not active_channel:
        print("Nenhum canal ativo para criar a thread.")
        return None
    
    try:
        existing_thread = await get_thread_for_task(task_key)
        
        thread_name = f"Task {task_key} - {task_summary}"
        if len(thread_name) > 100:
            thread_name = thread_name[:97] + "..."
        
        if existing_thread:
            # atualiza se a thread já existe
            current_thread_name = existing_thread.name
            current_summary = ""
            if " - " in current_thread_name:
                current_summary = current_thread_name.split(" - ", 1)[1]
            
            # verifica se o summary mudou no Jira
            if current_summary != task_summary:
                await existing_thread.edit(name=thread_name)
                print(f"Título da thread atualizado para {task_key} devido à alteração no Jira")
            
            if assignee:
                await mention_assignee(existing_thread, assignee)
            
            return existing_thread

        # criaçao de uma nova thread
        thread = await active_channel.create_thread(
            name=thread_name,
            auto_archive_duration=10080,  # 7 dias sem novas mensagens
            type=discord.ChannelType.public_thread 
        )
        
        task_thread_map[task_key] = thread.id
        save_task_thread_map()

        await thread.send(
            f"**{task_key}** - {task_summary}\n\n{os.getenv('JIRA_URL')}{task_key}"
        )   
        
        if assignee:
            await mention_assignee(thread, assignee)
        
        print(f"Nova thread criada para tarefa {task_key}")
        return thread

    except discord.Forbidden:
        print("Erro: O bot não tem permissão para criar threads neste canal.")
    except discord.HTTPException as e:
        print(f"Erro HTTP ao tentar criar/atualizar thread: {e}")
    return None

async def mention_assignee(thread, assignee):
    """
        thread: objeto de thread do discord
        assignee: responsável atribuido
    """
    if not assignee:
        print("Nenhum responsável atribuído à tarefa")
        return

    # converte p/ dicionario se for um objeto Pydantic
    if hasattr(assignee, 'model_dump'):
        assignee = assignee.model_dump()

    # lista para armazenar chaves de busca
    possible_keys = []
    display_name = None

    # extrai possiveis chaves de identificaçao
    keys_to_check = ['key', 'name', 'emailAddress', 'displayName']
    for key in keys_to_check:
        if isinstance(assignee, dict) and key in assignee and assignee[key]:
            possible_keys.append(assignee[key])
            if not display_name:
                display_name = assignee.get('displayName', assignee[key])
        elif hasattr(assignee, key) and getattr(assignee, key):
            possible_keys.append(getattr(assignee, key))
            if not display_name:
                display_name = getattr(assignee, 'displayName', getattr(assignee, key))

    # remove duplicatas e valores None
    possible_keys = list(set(filter(None, possible_keys)))

    discord_user_id = None
    matched_key = None
    
    for key in possible_keys:
        if key in user_mapping:
            discord_user_id = user_mapping[key]
            matched_key = key
            break

    if discord_user_id:
        print(f"Mapeamento encontrado: {matched_key} → {discord_user_id}")
        # verifica se ja existe uma menção para este usuário na thread
        last_message = None
        async for message in thread.history(limit=1):
            last_message = message

        # menciona apenas se a ultima mensagem não tiver a mesma menção
        if not last_message or f"<@{discord_user_id}>" not in last_message.content:
            await thread.send(f"<@{discord_user_id}> ")
        return

    # usa display name se não encontrar no mapeamento
    if not display_name and possible_keys:
        display_name = possible_keys[0]

    await thread.send(f"**{display_name}** foi atribuído como responsável por esta tarefa.")
    print("⚠️ Nenhum mapeamento encontrado. Verifique o mapeamento usando o comando /mapear_usuario")


# ----- Endpoints do FastAPI 

@app.post("/jira-webhook")
async def jira_webhook(data: JiraIssueUpdate):
    """
    endpoint que recebe as atualizações webhook do Jira e
    cria as threads no Discord quando uma tarefa é movida para "em andamento"
    """
    try:
        issue = data.issue
        # transforma o objeto "issue" em um dicionário usando model_dump()
        issue_dict = issue.model_dump()
        print(f"Webhook recebido: {issue.key}")

        status_name = issue.fields.status.name
        status_category = issue.fields.status.statusCategory.name
        print(f"Status: '{status_name}'; Categoria: '{status_category}' ")
        is_in_progress = status_name.lower() == "em andamento" or status_category.lower() == "in progress"
        
        if is_in_progress:
            task_key = issue.key
            task_summary = issue.fields.summary
            assignee = issue.fields.assignee
            print(f"Criando thread para {task_key}")
            
            # executa de forma assíncrona no loop do bot
            asyncio.run_coroutine_threadsafe(
                create_or_update_thread_from_jira(task_key, task_summary, assignee), 
                bot.loop
            )
            
            return {"status": "success", "message": f"Webhook processado: {issue.key}"}
        else:
            return {"status": "skipped", "message": "Tarefa não está em andamento"}
    
    except Exception as e:
        print(f"Erro ao processar webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ----- Eventos e comandos do Discord

@bot.event
async def on_ready():
    print(f'✅ Bot {bot.user} está online!')

    try:
        synced = await bot.tree.sync()
        print(f"Sincronizados {len(synced)} comando(s) com o Discord")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")
    
    print(f'FastAPI rodando em http://0.0.0.0:5000')
    print(f'Endpoints disponíveis:')
    print(f'  - /jira-webhook')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

@bot.tree.command(name="mapear_usuario", description="Associa um usuário do Jira a um usuário do Discord")
@app_commands.describe(


    jira_user="Email, username ou chave do usuário no Jira",

    discord_user="Usuário do Discord"
)
async def mapear_usuario(interaction: discord.Interaction, jira_user: str, discord_user: discord.Member):

    discord_user_id = str(discord_user.id)
    
    jira_user = jira_user.lstrip('@')

    user_mapping[jira_user] = discord_user_id
            
    save_user_mapping()

    await interaction.response.send_message(
        f"Usuário do Jira '{jira_user}' associado ao usuário do Discord {discord_user.mention}."
    )


@bot.tree.command(name="listar_mapeamentos", description="Lista todos os mapeamentos de usuários Jira-Discord")
async def listar_mapeamentos(interaction: discord.Interaction):

    if not user_mapping:
        await interaction.response.send_message("⚠️ Não há usuários mapeados.")
        return
    
    message = "📋 **Mapeamento de usuários Jira → Discord**:\n"
    for jira_user, discord_id in user_mapping.items():
        message += f"• **{jira_user}** → <@{discord_id}>\n"
    
    await interaction.response.send_message(message)

@bot.tree.command(name="remover_mapeamento", description="Remove a associação entre um usuário do Jira e do Discord")
@app_commands.describe(
    jira_user="Email ou username do usuário no Jira que será removido do mapeamento"
)
async def remover_mapeamento(interaction: discord.Interaction, jira_user: str): 

    if jira_user in user_mapping: #
        del user_mapping[jira_user]
        save_user_mapping()

        await interaction.response.send_message(
            f"✅ Remoção '{jira_user}' concluída com sucesso!"
        )
    else:
        await interaction.response.send_message(
            f"⚠️ Usuário '{jira_user}' não foi encontrado no mapeamento."
        )

@bot.tree.command(name="ativar", description="Ativa o bot no canal atual")
async def ativar(interaction: discord.Interaction):

    global active_channel
    
    if isinstance(interaction.channel, discord.TextChannel):
        active_channel = interaction.channel
        await interaction.response.send_message(
            f"✅ Bot ativado no canal #{interaction.channel.name}!"
        )
    else:
        await interaction.response.send_message(
            "⚠️ Este comando só pode ser usado em canais de texto."
        )

@bot.tree.command(name="desativar", description="Desativa o bot no canal atual")
async def desativar(interaction: discord.Interaction):

    global active_channel
    
    if active_channel and interaction.channel.id == active_channel.id:
        active_channel = None
        await interaction.response.send_message("❌ Bot desativado neste canal.")
    elif active_channel:
        await interaction.response.send_message("⚠️ O bot já está desativado.")
    else:
        await interaction.response.send_message("⚠️ O bot não está ativo em nenhum canal.")


# ----- Funções para inicialização da aplicação 

def run_fastapi():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)

def run_bot(): 
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure as e:
        print(f"Erro de login: {e}")
        print("Verifique se o token do bot está correto no arquivo .env")
    except Exception as e:
        print(f"Erro ao iniciar o bot: {e}")

if __name__ == "__main__":
    print("Iniciando aplicação...")
    # inicia fastApi em uma thread separada
    fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
    fastapi_thread.start()

    run_bot()