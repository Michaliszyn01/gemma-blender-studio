# Continuação no computador do usuário

Objetivo: validar e aperfeiçoar um modelador Blender local com Gemma no Ollama. Preserve o painel simples e o ciclo incremental de propostas, renders e revisão. Priorize qualidade visual verificável sobre número de operações ou horas de execução.

1. Leia `LEIA_PRIMEIRO.md`, `core.py`, `blender_worker.py` e `modeling_guide.txt`.
2. Confira as versões e caminhos reais do Python, Blender e Ollama. Consulte `/api/tags` e `/api/show` para escolher o modelo exato com visão. Não instale/troque modelos silenciosamente nem presuma uma tag do Gemma.
3. Rode os testes unitários e `validar_blender.py` com o Blender instalado. Corrija incompatibilidades de API identificadas nos logs.
4. Inicie o painel, verifique visualmente os estados e faça uma sessão REAL de 3 rodadas com uma peça simples, referência e prompt. Confira que as imagens chegam ao modelo, os JSONs são válidos, os renders refletem as ações e a versão anterior sobrevive a uma rejeição.
5. Teste uma cópia de um modelo existente do usuário, incluindo nomes, materiais, escalas e hierarquia. Não altere o original.
6. Só após isso avance para uma sessão longa. Não prometa modelo quase impecável; registre limites observados.

Melhorias futuras com maior retorno: calibração da câmera com a referência, catálogo visual de peças, ferramentas de silhueta customizada, medidas de proporção, comparação mais consistente, controle manual de aprovar/rejeitar versões, isolamento dos componentes, testes de interseção e exportação Roblox. Não implemente tudo antes de comprovar o primeiro ciclo real.

Arquitetura: `app.py` serve apenas localhost; `core.py` gerencia sessões; `blender_worker.py` roda dentro do Blender; `web/` é o painel. `modeling_guide.txt` é um prompt de sistema, não uma skill instalada.
