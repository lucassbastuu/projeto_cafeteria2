# Cafeteria

MVP local de cardápio e pedidos. Pagamento é apenas registrado.

## Executar

```bash
pip install -r requirements.txt
python app.py
```

Abra http://127.0.0.1:5000

O arquivo `cafeteria.db` é criado na primeira execução.

Fora do ambiente de desenvolvimento, defina `SECRET_KEY` e `FLASK_ENV=production` antes de subir o app. Sem `SECRET_KEY` em produção o processo não inicia. `debug` fica ativo somente quando `FLASK_ENV` é `development` (padrão local).
