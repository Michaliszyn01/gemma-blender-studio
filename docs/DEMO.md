# Verificação local e primeiro experimento

Em 28/10/2026, os **25 testes unitários/HTTP foram aprovados** em Python 3.12.14, numa cópia isolada do repositório público e com dados temporários. O teste HTTP abre o painel local e verifica o bootstrap, o controle de sessão e a rejeição de caminhos externos. Os testes do controlador simulam as integrações com modelos/Blender.

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Resultado observado:

```text
Ran 25 tests
OK
```

Isso **não** comprova geração real, fidelidade visual, desempenho de um modelo, compatibilidade com sua instalação do Blender ou importação em motor de jogo. Nenhum modelo foi chamado e nenhum .blend foi produzido nesta verificação.

## Primeiro teste manual sugerido

1. Instale os pré-requisitos e abra o painel conforme o README.
2. Informe o executável do Blender e a instalação local do Ollama/modelo.
3. Use uma referência que você tenha direito de usar e uma tarefa curta, como uma caixa simples.
4. Compare a prévia com a referência e confira os requisitos geométricos.
5. Abra o candidato salvo no Blender antes de aprovar o arquivo.

Esse roteiro é uma proposta de teste, não uma execução já realizada. O diagrama no README é ilustrativo; não é uma captura de tela do painel.
