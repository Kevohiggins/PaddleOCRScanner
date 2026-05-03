# PaddleOCR Scanner

Un escáner OCR ligero y potente, potenciado por **RapidOCR & ONNX**.

## ¿De qué va esto?

Este programa cumple la misma función que el OCR nativo de Windows, pero usando un motor mucho más robusto. Nació de la frustración pura: el OCR de Windows no me leía los menús de una novela visual con fondos complejos, así que armé esto.

PaddleOCR Scanner captura lo que tenés en pantalla y te permite navegar el texto detectado con el teclado, simulando un "cursor virtual" sobre los elementos.

## Atajos de Teclado Globales

*   `Ctrl + Alt + S` -> **Escaneo de Pantalla:** Captura absolutamente todo lo que se ve en tu monitor.
*   `Ctrl + Alt + W` -> **Escaneo de Ventana:** Enfoca el OCR únicamente en la ventana que tengas activa.
*   `Ctrl + Alt + D` -> **Escaneo Dinámico:** Activa la lectura en tiempo real. Vigila la pantalla en bucle y te avisa cuando detecta cambios (ideal para seguir subtítulos).
*   `Ctrl + Shift + C` -> **Configuración:** Abre el panel para cambiar resoluciones, atajos y zonas de recorte.
*   `Ctrl + Alt + Q` -> **Cerrar Programa:** Apaga el scanner por completo.

## ¿Cómo navegar por los resultados?

Cuando hacés un escaneo estático (S o W), el programa te avisa cuántos bloques de texto encontró. A partir de ahí:

*   **Flechas Arriba / Abajo:** Te movés entre las líneas de texto detectadas.
*   **Enter:** Hace un click izquierdo real justo donde está el texto.
*   **Shift + Enter:** Hace doble click izquierdo.
*   **Tecla Aplicaciones:** Simula un click derecho.

*(Nota: De momento, la navegación es por líneas/bloques completos. Todavía no permite la lectura palabra por palabra).*

## Aclaración importante

Para que el programa pueda capturar teclas globales y hacer clicks en ventanas que tienen privilegios elevados (como el Administrador de Tareas o instaladores), **es necesario ejecutar PaddleOCR Scanner como Administrador**.

## Créditos y Apoyo

Quiero dejar en claro que yo no escribí el código de esto. Todo fue programado por **Gemini**, la inteligencia artificial de Google. Mi trabajo fue idear el proyecto, promptear como un desgraciado, testear y reportar bugs.

Si este programa te salvó las papas y querés bancarme con una birra, podés hacerlo acá:
*   [Mercado Pago](https://link.mercadopago.com.ar/kevohiggins) (Si sos de Argentina)
*   [PayPal](https://www.paypal.com/paypalme/KevOHiggins) (Si sos de afuera)

¿Encontraste algún bug, tenés sugerencias o querés charlar? Pasate por mi [formulario de contacto](https://kevohiggins.github.io/contactame).