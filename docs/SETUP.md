# Setup

## Instalação de dependências

Use **exatamente** este comando:

```bash
python -m pip install -r requirements.txt
```

## Erro comum

Se você rodar algo como:

```bash
python -m pip install requirements txt
```

o `pip` tenta instalar pacotes chamados `requirements` e `txt` (em vez de ler o arquivo), e retorna erro.

## Se ainda falhar

Tente atualizar o pip e reinstalar:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Aviso sobre PyNaCl

Se aparecer a mensagem:

`PyNaCl is not installed, voice will NOT be supported`

isso significa que o pacote de voz opcional do Discord não está instalado no ambiente.

Este projeto já inclui `PyNaCl` no `requirements.txt`. Após instalar as dependências com `-r`, o aviso deixa de aparecer.
