# -*- coding: utf-8 -*-
"""
Implementaciones intercambiables del contrato de permisos (RNF-03).

- :mod:`windows`: producción. Sondea el permiso abriendo un manejador bajo
  suplantación, de modo que la decisión la toma el kernel.
- :mod:`memoria`: doble de prueba. No toca el sistema operativo.
"""
