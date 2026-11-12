# Catálogo de Kosmos Cosmética para ChatGPT

Todos los días a las 6:00 (Argentina) `chatgpt_feed.py` lee los productos
publicados de Tiendanube y arma el archivo con el formato de OpenAI. El
workflow lo publica en https://kosmos-cosmetica.github.io/kosmos-feed/chatgpt_productos.csv,
que es el link cargado en ChatGPT Business Hub → Productos.

Solo datos públicos de la tienda: productos, precios, stock (sí/no), imágenes
y links. Las credenciales son secrets del repo y no están en el código.
