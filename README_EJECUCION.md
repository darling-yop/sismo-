# SismoLab AVL - Guía de inicio (Windows)

## 1. Cómo iniciar el programa

1. Asegúrate de tener instalado Python 3.12 o una versión superior.
2. Abre una terminal en la carpeta del proyecto.
3. Ejecuta el siguiente comando:

   `python main.py`

4. Se abrirá la interfaz del programa, desde donde podrás utilizar sus funciones.

## 2. Archivos de prueba

En la pestaña **«Archivos y versiones»**, puedes seleccionar diferentes archivos para probar el funcionamiento del programa.

- **Inserciones:** permite probar árboles con datos aleatorios, ordenados de menor a mayor o de mayor a menor.
- **Topologías:** permite probar diferentes estructuras de árboles, incluidas algunas que el programa debe rechazar por ser inconsistentes.
- **Ráfagas:** permite probar una secuencia de operaciones. Primero, carga `estado_inicial_rafaga.json` en la pestaña de topología y después `rafaga_mixta.json` en la pestaña «Cola».

## 3. Información para desarrolladores

Para ejecutar las pruebas automáticas, generar los archivos de datos y comprobar los resultados esperados, consulta las instrucciones técnicas del proyecto.