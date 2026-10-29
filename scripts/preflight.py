"""Read-only local Compose admission checks. Never install runtimes or restart Docker."""
import argparse
import json
import re
import socket
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PORTS=(8000,8080)

def command(args):
    try:
        reply=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=20)
        return reply.returncode,reply.stdout
    except (OSError,subprocess.TimeoutExpired):return -1,''

def occupied(port):
    with socket.socket() as connection:
        connection.settimeout(.5)
        return connection.connect_ex(('127.0.0.1',port))==0

def inspect_environment(project='debugych-local',run=command,is_occupied=occupied):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',project):raise ValueError('Invalid Compose project name')
    checks=[]
    def add(name,ok,message):checks.append({'check':name,'ok':ok,'message':message})
    code,raw=run(['docker','info','--format','{{json .}}'])
    try:info=json.loads(raw) if code==0 else {}
    except (ValueError,TypeError):info={}
    if not isinstance(info,dict):info={}
    if not info:
        add('docker',False,'Docker Engine недоступен. Проверьте запуск Docker и права доступа. Ничего не перезапущено.')
        return {'ready':False,'checks':checks}
    add('linux_engine',info.get('OSType')=='linux','Нужен Linux Docker Engine с поддержкой runsc; Windows containers не поддерживаются.')
    add('gvisor',isinstance(info.get('Runtimes'),dict) and 'runsc' in info['Runtimes'],'runsc должен быть зарегистрирован на Docker-хосте. Автоматического перехода на runc нет.')
    code,raw=run(['docker','compose','version','--short'])
    match=re.search(r'(\d+)\.(\d+)\.(\d+)',raw)
    add('compose',code==0 and bool(match) and tuple(map(int,match.groups()))>=(2,24,4),'Нужен Docker Compose 2.24.4 или новее.')
    if not checks[-1]['ok']:return {'ready':False,'checks':checks}
    code,_=run(['docker','compose','--project-name',project,'-f','docker-compose.yml','config','--quiet'])
    add('configuration',code==0,'Compose-конфигурация должна быть корректной. Значения переменных и секреты не выводятся.')
    # Only inspect containers carrying this application's explicit project label.
    code,raw=run(['docker','ps','--filter','label=com.docker.compose.project='+project,'--format','{{.ID}}'])
    owned=set()
    for identity in raw.split() if code==0 else []:
        if not re.fullmatch(r'[a-f0-9]{12,64}',identity):continue
        status,value=run(['docker','inspect','--format','{{json .NetworkSettings.Ports}}',identity])
        try:bindings=json.loads(value) if status==0 else {}
        except (ValueError,TypeError):bindings={}
        if isinstance(bindings,dict):
            for items in bindings.values():
                if not isinstance(items,list):continue
                for item in items:
                    if isinstance(item,dict) and str(item.get('HostPort','')).isdigit() and item.get('HostIp') in ('127.0.0.1','0.0.0.0','::'):
                        owned.add(int(item['HostPort']))
    for port in PORTS:
        add('port_'+str(port),not is_occupied(port) or port in owned,f'Порт {port} должен быть свободен либо принадлежать контейнеру проекта {project}. Чужие процессы не останавливаются.')
    return {'ready':all(c['ok'] for c in checks),'checks':checks}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',default='debugych-local')
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    try:result=inspect_environment(args.project)
    except ValueError:parser.error('Имя проекта: строчные буквы, цифры, дефис или подчёркивание, до 64 символов.')
    if args.json:print(json.dumps(result,ensure_ascii=False))
    else:
        for check in result['checks']:print(('OK' if check['ok'] else 'STOP')+' '+check['check']+': '+check['message'])
        print('Проверка регистрации runtime не заменяет реальный gVisor smoke. Подготовка хоста: docs/quickstart.md')
    raise SystemExit(0 if result['ready'] else 1)
