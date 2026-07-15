# Engenharia API

API REST em Python 3.12 + FastAPI para leitura e interpretação de documentos de engenharia civil: **plantas baixas** e **relatórios de sondagem SPT**. Aceita PDF, PNG, JPG/JPEG e TIFF, e retorna resultados estruturados em JSON, prontos para integração com aplicações web (incluindo sites no GitHub Pages).

## Instalação

### Requisitos

- Python 3.12
- Tesseract OCR (fallback do EasyOCR):
  - Ubuntu/Debian: `sudo apt install tesseract-ocr tesseract-ocr-por`
  - Windows: instalador em https://github.com/UB-Mannheim/tesseract/wiki
  - macOS: `brew install tesseract tesseract-lang`

### Passo a passo

```bash
git clone <seu-repositorio>
cd engenharia-api

python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env             # ajuste as variáveis conforme necessário

uvicorn app.main:app --reload
```

A API sobe em `http://localhost:8000`. Na primeira análise com OCR, o EasyOCR baixa os modelos automaticamente (~100 MB); se indisponível, o Tesseract é usado como fallback.

### Docker

```bash
docker build -t engenharia-api .
docker run -p 8000:8000 --env-file .env engenharia-api
```

## Documentação automática

| URL | Conteúdo |
|---|---|
| `/docs` | Swagger UI interativo, com exemplos e teste de upload |
| `/redoc` | Documentação ReDoc |
| `/openapi.json` | Especificação OpenAPI 3 |

## Endpoints

### `GET /api/v1/status`

```json
{ "status": "online", "versao": "1.0.0", "modulos": ["planta", "sondagem"] }
```

### `POST /api/v1/planta/analisar`

Envia PDF ou imagem de planta baixa (campo `arquivo`, multipart/form-data).

```bash
curl -X POST http://localhost:8000/api/v1/planta/analisar \
  -F "arquivo=@planta.pdf"
```

Resposta (resumida):

```json
{
  "arquivo": "planta.pdf",
  "total_plantas": 1,
  "plantas": [
    {
      "frente": 12.50,
      "fundos": 12.40,
      "lateral_direita": 25.00,
      "lateral_esquerda": 25.10,
      "area_construida": 182.40,
      "escala": "1:100",
      "pavimentos": 1,
      "cotas": [
        { "valor": 3.50, "texto_original": "350", "orientacao": "horizontal", "confianca": 0.91, "posicao": [412.0, 780.5, 448.0, 796.0] }
      ],
      "ambientes": [
        { "nome": "Sala", "area": 25.30, "confianca": 0.95 }
      ],
      "avisos": []
    }
  ],
  "tempo_processamento_s": 4.21
}
```

PDFs com múltiplas plantas retornam uma entrada por planta na lista `plantas`.

### `POST /api/v1/sondagem/analisar`

```bash
curl -X POST http://localhost:8000/api/v1/sondagem/analisar \
  -F "arquivo=@sondagem.pdf"
```

Resposta (resumida):

```json
{
  "arquivo": "sondagem.pdf",
  "total_furos": 1,
  "furos": [
    {
      "furo": "SP-01",
      "profundidade_inicial": 0.0,
      "profundidade_total": 18.00,
      "nivel_agua": 3.20,
      "presenca_agua": true,
      "camadas": [
        { "inicio": 0.00, "fim": 2.00, "solo": "Argila Mole", "solo_normalizado": "argila", "nspt": 3, "umidade": "úmida" },
        { "inicio": 2.00, "fim": 5.00, "solo": "Silte Arenoso", "solo_normalizado": "silte", "nspt": 8, "umidade": "pouco úmido" }
      ],
      "nspt_por_metro": { "1.00": 3, "2.00": 4 },
      "avisos": []
    }
  ],
  "tempo_processamento_s": 2.87
}
```

O classificador de solos reconhece argila, areia, silte, pedregulho, rocha, solo residual, laterítico e orgânico mesmo com variações de nomenclatura (ex.: "ARGILA SILTOSA MOLE CINZA" → `argila`).

## Integração com GitHub Pages

O GitHub Pages hospeda apenas conteúdo estático; a API precisa rodar em um serviço de backend (Render, Railway, Fly.io, VPS etc.). No frontend:

```javascript
const form = new FormData();
form.append("arquivo", inputFile.files[0]);

const resposta = await fetch("https://sua-api.onrender.com/api/v1/planta/analisar", {
  method: "POST",
  body: form,
});
const dados = await resposta.json();
```

Em produção, restrinja o CORS no `.env`:

```
API_CORS_ORIGINS=["https://seuusuario.github.io"]
```

## Arquitetura

```
app/
├── main.py            # FastAPI, middlewares (CORS, GZip, logs, erros)
├── api/v1/rotas.py    # Endpoints (sem lógica de processamento)
├── services/          # planta_service.py, sondagem_service.py
├── schemas/           # Contratos Pydantic de entrada/saída
├── models/            # Modelos de domínio internos
├── ocr/engine.py      # EasyOCR + fallback Tesseract + correção de erros
├── vision/            # PyMuPDF/pdfplumber (documentos) + OpenCV (paredes/cotas)
├── utils/             # validação de upload, cache TTL, JWT, rate limit, logs
└── config/settings.py # Configurações via variáveis de ambiente
```

Recursos implementados: processamento assíncrono (páginas em paralelo via `asyncio.to_thread`), cache por hash do arquivo, compressão GZip, rate limit por IP, validação de assinatura real do arquivo (magic bytes), JWT opcional, logs estruturados com request-id.

## Testes

```bash
pytest -v
```

Cobertura: status, upload de PDF e imagem, leitura de cotas com correção de OCR, leitura de NSPT e camadas, PDFs inválidos, arquivo vazio/grande, falhas de OCR (degradação graciosa) e cache.

## Limitações e evolução

A detecção visual de frente/fundos/laterais usa heurísticas (contorno externo + posição das cotas) que funcionam bem em plantas residenciais convencionais, mas plantas complexas ou digitalizações de baixa qualidade podem exigir revisão dos resultados — o campo `avisos` sinaliza inferências e falhas. Pontos naturais de evolução: modelo de detecção de objetos treinado para símbolos de planta, Redis para cache distribuído e fila (Celery/RQ) para arquivos grandes.
