"""Exportação privada e verificação portátil do diário BB-EVENT-1."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.request import Request, build_opener, ProxyHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bbcore.events import Events
from bbcore.store import Conflict, stamp


def save_private(path, value):
    with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'w') as output:
        output.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    export = commands.add_parser('export', help='Exportar diário local e checkpoint, sem sobrescrever arquivos')
    export.add_argument('destination', type=Path)
    verify = commands.add_parser('verify', help='Verificar cadeia exportada; evidências externas não são revalidadas')
    verify.add_argument('journal', type=Path)
    verify.add_argument('--checkpoint', type=Path)
    args = parser.parse_args()
    if args.action == 'verify':
        bundle = json.loads(args.journal.read_text())
        checkpoint = json.loads(args.checkpoint.read_text()) if args.checkpoint else None
        print(json.dumps(Events.verify_bundle(bundle, checkpoint), ensure_ascii=False))
        print('Referências externas não revalidadas. Integridade não comprova veracidade ou autoria.')
        if checkpoint is None:
            print('Sem checkpoint independente: não detecta reescrita integral com hashes recalculados.')
        return
    destination = args.destination.expanduser()
    checkpoint_path = destination.with_name(destination.name + '.checkpoint.json')
    if destination.exists() or checkpoint_path.exists():
        raise FileExistsError('Destino ou checkpoint já existe; escolha novos nomes')
    config = dict(line.split('=', 1) for line in (Path.home()/'.config/bb-core/secret.env').read_text().splitlines()
                  if '=' in line and not line.startswith('#'))
    request = Request('http://127.0.0.1:8789/api/events/export', headers={'Authorization': 'Bearer '+config['BB_READ_TOKEN']})
    with build_opener(ProxyHandler({})).open(request, timeout=30) as response:
        bundle = json.load(response)
    Events.verify_bundle(bundle)
    checkpoint = {'schema': 'BB-EVENT-1', **{key: bundle['head'][key] for key in ('journal_id', 'last_seq', 'last_hash')},
                  'exported_at': stamp()}
    save_private(destination, bundle)
    save_private(checkpoint_path, checkpoint)
    print('Diário privado:', destination)
    print('Checkpoint:', checkpoint_path)
    print('Guarde o checkpoint em local independente para verificar reescritas futuras; este arquivo não é assinado.')


if __name__ == '__main__':
    try:
        main()
    except (Conflict, ValueError, OSError) as error:
        raise SystemExit(str(error)) from error
