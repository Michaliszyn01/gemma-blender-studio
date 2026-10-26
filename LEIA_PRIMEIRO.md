# Gemma Blender Studio — v0.1

**Validação local de 20/10/2026:** veja `DIAGNOSTICO_2026-10-20.md`. O bloqueio de resposta vazia foi corrigido e o ciclo Ollama + Blender executado. Os 17 testes passam, mas a qualidade visual e a autoavaliação continuam insuficientes para sessões noturnas. Nova operação: `tapered_box`, para volumes afunilados com parâmetros compactos. A seção de limitações da entrega anterior abaixo é histórica.

Aplicativo local para construir ou melhorar modelos no Blender com um modelo multimodal do Ollama. Painel em português com referência, prompt, arquivo .blend opcional, prévias, versões e histórico. O Factory Kit 3.0 está incluído.

## Começar no Windows

1. Extraia este ZIP inteiro para uma pasta local, por exemplo `Documentos/GemmaBlenderStudio`. Não execute dentro do ZIP.
2. Instale Python 3.11 ou superior, com o launcher `py`, e Blender 4.2 ou superior. Essa é a compatibilidade alvo; execute o teste local abaixo para conferir sua versão.
3. Abra o Ollama e instale/tenha um modelo que suporte imagens. O aplicativo lista os nomes exatos instalados; não presume uma tag específica para Gemma.
4. Clique duas vezes em `INICIAR_WINDOWS.bat`. Na primeira vez ele prepara um ambiente Python e instala Pillow; essa instalação exige internet. Depois o aplicativo funciona localmente, sem API paga.
5. O navegador abre o painel. Em **Configurações**, escolha o modelo e cole o caminho completo do `blender.exe`, sem aspas. Clique em **Testar conexões**. Isso consulta as capacidades do modelo e a versão do Blender, mas ainda não gera um render.
6. Execute `TESTAR_BLENDER_WINDOWS.bat` para verificar criação, edição, material, malha customizada, salvamento, reabertura e três renders no seu Blender. Ele usa o caminho salvo após uma sessão iniciada ou pede o caminho no terminal. Confira também as imagens em `data/blender-smoke-test`.
7. Adicione uma referência e escreva o prompt. Para melhorar um modelo existente, carregue um `.blend` descomprimido de até 180 MB. Salve uma cópia sem compressão no Blender se o upload não reconhecer o arquivo.
8. **Primeiro teste recomendado:** 3 rodadas, 0,25 hora e uma peça simples. Confira proporções, materiais e encaixes antes de aumentar para uma sessão noturna.

No Linux/macOS: execute `sh iniciar.sh`, configure o executável do Blender e faça o teste com `python validar_blender.py /caminho/do/blender` no ambiente virtual.

## Como trabalha

O controlador envia a referência, o estado da cena e as imagens da última versão aceita ao Ollama. O modelo retorna um lote estruturado com até 24 operações. O aplicativo valida as operações, executa-as num processo separado do Blender e salva um candidato com três vistas. O modelo compara o candidato com a referência e a versão aceita anterior. Se aceitar, o candidato vira a versão atual; se rejeitar, a anterior continua sendo usada.

O arquivo `modeling_guide.txt` contém o guia de modelagem: silhueta, proporções, encaixes, acabamento e identidade entre módulos. É uma instrução carregada pelo aplicativo em cada chamada, não um treinamento dos pesos nem uma skill instalada no ChatGPT.

Operações implementadas: caixas, cilindros, cones, esferas, toros, malhas customizadas pequenas, transformação, material, chanfro, exclusão e importação de assets do catálogo. Não há execução de código Python gerado pelo modelo.

O Factory Kit é extraído automaticamente e prioriza os arquivos GLB com seus materiais. O catálogo enviado ao modelo usa identificadores e nomes das peças. Nesta versão não há busca visual por miniaturas nem escolha manual de subconjuntos do catálogo.

Para cenas importadas, os nomes dos objetos são normalizados para identificadores ASCII na cópia de trabalho. O arquivo original não é alterado. Câmeras, luzes e objetos cujo nome começa com `SYS_` são substituídos por um conjunto de inspeção. Não use esse prefixo para a geometria que deseja preservar. Os três renders usam enquadramento automático, não calibração exata da câmera da referência.

## Controles e versões

- **Parar:** interrompe a execução do Blender; se estiver aguardando Ollama, aguarda o retorno ou o timeout configurado. Não fecha o servidor Ollama.
- **Retomar sessão:** usa o último projeto do painel e a última versão aceita. Usa as configurações atuais e um novo orçamento de rodadas/tempo; não importa um novo prompt ou referência.
- **Abrir no Blender:** abre a última versão aceita com execução automática de scripts desativada.
- **Versões:** clicar numa rodada mostra seu candidato, inclusive os rejeitados. **Ver última aceita** retorna à prévia atual. O botão principal de download sempre entrega a última versão aceita, independentemente da prévia selecionada.
- Fechar a aba do navegador não para o processo. Mantenha o terminal aberto e desative a suspensão automática do PC se for trabalhar durante a noite.
- Fechar o terminal interrompe a sessão. Ao reabrir o aplicativo, a última sessão é marcada como interrompida e pode ser retomada. Candidatos já gravados ficam no disco.
- O aplicativo encerra quando chega ao limite de rodadas/tempo, após 4 candidatos rejeitados seguidos, 3 falhas consecutivas, pedido de parada ou quando o modelo declara conclusão. Um processo de render tem limite de 5 minutos. O tempo máximo pode ultrapassar o orçamento enquanto uma chamada do Ollama termina, até o timeout configurado.

Arquivos persistidos localmente em `data/jobs/<sessão>/`: referência, .blend de entrada opcional, propostas, revisões, logs, imagens e modelos de cada rodada. O painel mostra somente a sessão mais recente; sessões anteriores continuam no disco. Não apaga versões automaticamente. Elas podem ocupar bastante espaço.

## Expectativas e limites

Esta é uma primeira implementação, não um modelador profissional validado. O controlador e o servidor passaram por 14 testes automatizados nesta entrega. A sintaxe de Python e JavaScript também foi verificada. Os testes simulam Ollama e Blender; não foi possível executar inferência, renderização real ou validação visual do painel no ambiente de criação, pois esses componentes não estavam disponíveis. Por isso existe o teste local de renderização.

A nota visual é a opinião do próprio modelo e não uma medida objetiva de fidelidade. Uma revisão aceita pode estar errada. Tempo extra e mais rodadas não garantem melhoria contínua. Compare o resultado com a referência antes de usar no jogo.

Não há escultura orgânica avançada, retopologia automática, UV inteligente, rigging, animação, exportação automática para Roblox ou reconstrução 3D exata a partir de uma foto nesta versão. Há limite de 200 objetos/grupos editáveis; cenas grandes precisam ser simplificadas. As malhas customizadas têm limite de 512 vértices por operação. Não há verificação completa de interseções, malha manifold ou compatibilidade entre todos os encaixes.

A RTX 5070 de 12 GB será usada pelo Ollama conforme sua configuração. O aplicativo não garante que qualquer quantização/contexto do Gemma caiba na VRAM. Comece com contexto 8192 e observe o consumo. As prévias usam Cycles na CPU, com poucas amostras, para não disputar VRAM com o modelo. A qualidade final precisa ser inspecionada no Blender.

## Desenvolvimento no Codex local

Abra esta pasta no Codex no seu computador e peça para ler `CONTINUAR_NO_CODEX.md`. O código é Python com servidor HTTP padrão e Pillow. O painel usa HTML/CSS/JS sem dependências de frontend, fontes externas ou compilação.

Testes: `python -m unittest discover -s tests -v`.

Documentação consultada em 20/10/2026:
- https://docs.ollama.com/api/chat
- https://github.com/ollama/ollama/blob/main/docs/api.md
- https://docs.blender.org/manual/en/dev/advanced/command_line/arguments.html
- https://docs.blender.org/api/main/bpy.types.BlendDataLibraries.html
- https://docs.blender.org/api/main/bpy.ops.render.html

## Licenças

O aplicativo é disponibilizado sob MIT; veja `LICENSE`. O pacote Kenney Factory Kit 3.0 tem licença CC0, com o arquivo original `License.txt` dentro de `assets/factory.zip`. Autor: Kenney, https://kenney.nl. Não inclui os robôs enviados pelo usuário nem o modelo RZ-01 do BlendSwap.
