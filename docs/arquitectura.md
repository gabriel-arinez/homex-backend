# Arquitectura

Django REST Framework expone el dominio comercial. PostgreSQL es la autoridad
para totales, estados, stock, recibos y restricciones concurrentes. Los servicios
Django coordinan transacciones y convierten errores comerciales PostgreSQL en
respuestas 400; Vue sólo presenta datos y nunca recalcula reglas autoritativas.

Las migraciones son el único bootstrap operativo. Redis/NLP permanecen fuera del
flujo manual hasta F08.
