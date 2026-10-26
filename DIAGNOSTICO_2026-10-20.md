# Diagnóstico e validação real — 20/10/2026

O bloqueio inicial de integração foi reproduzido e corrigido. O ciclo real executa, mas a qualidade do tronco e a confiabilidade da avaliação automática continuam insuficientes. **Não validado para sessões noturnas.**

## Primeira falha

Sessão original: `data/jobs/20261020-141648-a54e44`.

- O prompt é o tronco solicitado; `source` é nulo. A referência é efetivamente a imagem do tronco cinza, sem membros.
- As três pastas de rodada têm apenas `error.json`: falha de JSON no planejamento. Não existiam proposta válida, requisição ao Blender, revisão, log do Blender, cena, render ou `.blend`.
- `data/state.json` registra falhas entre 14:16:48 e 14:19:03, sem versão aceita.
- `data/settings.json` registra **40 rodadas, 8 horas, contexto 32000, timeout 600 s**. A versão original não gravava configurações por sessão; portanto essa é a configuração global persistida disponível, não um histórico imutável da execução.
- Não foi uma falha de geometria ou renderização nessa tentativa: o Blender sequer foi chamado.

Reprodução fiel da primeira chamada: `diagnostics/original-request.json` e `original-response.json`. O servidor respondeu com `done=true`, `done_reason=length`, `eval_count=4096`, conteúdo final vazio e 10643 caracteres no campo de raciocínio. O `/api/show` confirma que esse modelo habilita raciocínio por padrão.

Isso reproduz o mecanismo compatível com os erros originais. As respostas originais foram descartadas pelo aplicativo antigo; não é possível provar retrospectivamente o conteúdo exato de cada uma das três respostas antigas.

## Ambiente confirmado

| Item | Verificação local |
|---|---|
| Python do aplicativo | 3.14.4, `.venv/Scripts/python.exe` |
| Instalação base Python | `C:\Users\Eduardo\AppData\Local\Python\pythoncore-3.14-64` |
| Ollama | 0.40.6, `http://127.0.0.1:11434` |
| Executável Ollama | `C:\Users\Eduardo\AppData\Local\Programs\Ollama\ollama.exe` |
| Modelo exato | `gemma4:12b-it-q4_K_M`, 11.9B, Q4_K_M |
| Digest do modelo | `6114515d63c17436a7c0417d82820ac65ad643e2806c5a3c89cb62846436ed0b` |
| Capacidades anunciadas | completion, vision, audio, tools, thinking |
| Blender | 5.2.2 LTS, hash `d13f752e3b9c` |
| Executável Blender | `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe` |

Dados completos em `diagnostics/version.json`, `tags.json`, `show.json`.

O teste de visão usou o mesmo texto neutro com a referência e uma imagem branca de controle. Sem o prompt do tronco, o modelo descreveu corretamente o objeto cinza, os cilindros horizontais laterais e o estreitamento inferior. Com a imagem vazia disse que não havia objetos, mas errou sua cor, chamando-a de preta. Há evidência de processamento visual, não de percepção infalível. Registros em `diagnostics/vision`.

## Correções

1. `core.py`: consulta suporte a `think=false` e o usa nas chamadas estruturadas. Não aumenta rodadas, contexto nem orçamento de geração para esconder a causa.
2. Preserva resposta bruta e manifesto de cada chamada, incluindo ordem das imagens, caminhos e SHA-256 do arquivo e dos bytes enviados. Distingue truncamento, resposta vazia e JSON inválido; bloqueia a execução de conteúdo incompleto. Propostas inválidas também ficam disponíveis.
3. Grava configuração, informações do modelo e estado por sessão. Retomadas têm configuração própria registrada.
4. Explicita a cena aceita e os nomes editáveis após rejeição. Não promove candidatos rejeitados. Sessões sem versão aceita terminam com aviso correto.
5. `blender_worker.py`: relata centro e limites globais da geometria. A origem de uma malha com vértices deslocados não é seu centro visual; o relatório antigo favorecia conclusões incorretas sobre posição.
6. Acrescenta `tapered_box`: bloco fechado com oito vértices, afunilamento parametrizado, dimensões, transformação, material e chanfro. Isso atende volumes afunilados sem exigir longas listas de vértices. Não é um tronco pré-fabricado nem substituição do modelo.
7. Restringe comprimentos de vetores e limites de malhas no schema enviado, além da validação local.
8. Novas configurações começam com 3 rodadas / 0,25 h. Configurações existentes do usuário foram preservadas.

A necessidade da ferramenta compacta foi confirmada em uma execução intermediária: mesmo sem raciocínio, o modelo entrou em repetição de vértices até truncar. Essas respostas estão em `diagnostics/real-20261020-142810`. A malha customizada original consegue expressar o formato; o problema adicional é a confiabilidade da geração extensa de coordenadas.

Referência da API usada para o controle de raciocínio: [documentação oficial Ollama](https://docs.ollama.com/api/chat).

## Execuções reais e qualidade

Todas usaram a mesma referência, prompt, tag de modelo e contexto 32000; sem `.blend` inicial. Cada execução foi isolada em `diagnostics`, preservando a sessão original e o estado do painel.

| Execução | Resultado |
|---|---|
| `real-20261020-142556` | Rodadas 1 e 2 construídas/renderizadas/rejeitadas (45/100); rodada 3 bloqueada por tentar excluir objetos inexistentes após rejeição. |
| `real-20261020-142810` | Rodada 1 renderizada/rejeitada (65/100); rodadas 2 e 3 truncadas em listas de vértices, corretamente bloqueadas. |
| `real-20261020-143123` | Rodada 1 aceita pelo modelo (85/100); rodada 2 bloqueada por nome duplicado; rodada 3 editada sobre o `.blend` da rodada 1 e aceita pelo modelo (85/100). |

Na execução final o modelo declarou conclusão na primeira rodada. A sessão foi retomada por mais duas rodadas, com `stop_when_finished=false` somente no executor de validação, para completar o teste incremental. Esse controle não muda o comportamento padrão do painel.

Pasta da sessão final: `diagnostics/real-20261020-143123/jobs/20261020-143123-316f06`.

**Inspeção visual independente da nota do Gemma:** a versão final ainda apresenta ombros verticais em vez de horizontais, encaixe de pescoço separado, espaços entre volumes, afunilamento do abdômen no sentido inadequado e peito muito simples comparado à referência. A terceira rodada apenas reduz algumas dimensões e não demonstra melhoria convincente. A revisão que afirma encaixes corretos e silhueta muito próxima está errada.

As vistas frontal e lateral deixam os espaços evidentes. A perspectiva, com elevação maior que a referência, mascara alguns deles. Iluminação e enquadramento permitem inspecionar a forma, mas não são calibrados à câmera da referência. Renderização bem-sucedida não comprova fidelidade.

Arquivos finais:

- `iteration-001/{front,side,perspective}.png` e `model.blend`: primeira versão aceita pelo modelo.
- `iteration-002/proposal.json` e `error.json`: operação inválida preservada, sem execução.
- `iteration-003/{front,side,perspective}.png` e `model.blend`: resultado incremental final, **não aprovado visualmente por esta análise**.
- `planning-request.json` / `review-request.json`: referência primeiro; no review, candidato frontal/perspectiva em posições 2–3 e versão aceita anterior em 4–5.
- `planning-response.json` / `review-response.json`: respostas completas das rodadas finais que chegaram ao Blender.

SHA-256 da referência original e das cópias de validação: `9d0f119124b7cb0cc112d45f5772038c72073053b0889be52db148ddf60e5b46`.

## Verificação

- **17 testes automatizados passaram**: validação, servidor HTTP, rejeição, interrupção, truncamento e diagnóstico, ordem das imagens, estado sem aceitação e contrato de afunilamento. Dependências externas são simuladas nessa suíte.
- **Blender real**: `validar_blender.py` criou, salvou, reabriu, editou e renderizou três vistas; log em `diagnostics/blender-smoke.log`.
- **Geometria no Blender real**: `tests/blender_geometry_check.py` verificou dimensões, cilindro girado 90° em Y, edição de dimensões com rotação, malha deslocada, limites globais, materiais, chanfros, proporção de afunilamento e normais externas. Log em `diagnostics/geometry-check.log`.
- **Rejeição com Blender real e decisão controlada**: foi construído um candidato alterado sobre um `.blend` existente. A rejeição não mudou o caminho aceito nem seu conteúdo; SHA-256 antes/depois idêntico. Esse teste simula apenas a decisão do revisor, não o Blender. Evidência em `diagnostics/rollback/verification.json`.
- **Ollama + Blender reais**: planejamento, JSON, construção, renders, revisão e salvamento confirmados; a terceira rodada final reabriu a versão anterior real. As rejeições reais das execuções iniciais mantiveram a cena aceita vazia.

## Limites e uso

O aplicativo executa o ciclo, mas ainda não demonstra geração confiável do tronco pedido nem melhoria monotônica. A autoavaliação pode aprovar falhas óbvias; não deve decidir sozinha se o modelo está pronto. Persistem erros do modelo em posições, rotações, proporções e operações sobre nomes existentes. Não há teste geral de contato/interseção ou aprovação humana obrigatória.

Não foi fornecido outro `.blend` original do usuário para testar importação de uma cena externa complexa. O caminho incremental foi verificado com arquivos produzidos nesta validação.

Reinicie o servidor para carregar as correções. Os resultados de diagnóstico estão separados do painel para não substituir sua tentativa original. O `.blend` da rodada 3 pode ser aberto para inspeção, mas não é uma entrega visual aprovada. O próximo trabalho deve tratar avaliação objetiva de contatos/orientação e aprovação humana, antes de sessões longas.
