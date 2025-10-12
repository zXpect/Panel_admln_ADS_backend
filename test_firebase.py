"""
Script para probar la conexión a Firebase
Ejecutar desde la raíz del proyecto: python test_firebase.py
"""

import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'admin_panel.settings')
django.setup()

from worker_verification.services.firebase_service import firebase_service

print("Probando conexión a Firebase...")
print("-" * 50)

try:
    # Probar conexión a Realtime Database
    print("\n1. Probando Realtime Database...")
    workers = firebase_service.get_data('User/Trabajadores')
    
    if workers:
        print(f"Conexión exitosa!")
        print(f"   Trabajadores encontrados: {len(workers)}")
        
        # Mostrar primer trabajador
        first_worker_id = list(workers.keys())[0]
        first_worker = workers[first_worker_id]
        print(f"\n   Ejemplo de trabajador:")
        print(f"   - ID: {first_worker_id}")
        print(f"   - Nombre: {first_worker.get('name', 'N/A')}")
        print(f"   - Email: {first_worker.get('email', 'N/A')}")
        print(f"   - Trabajo: {first_worker.get('work', 'N/A')}")
    else:
        print("No se encontraron trabajadores, pero la conexión funciona")
    
    # Probar clientes
    print("\n2. Probando datos de Clientes...")
    clients = firebase_service.get_data('User/Clientes')
    
    if clients:
        print(f"Clientes encontrados: {len(clients)}")
    else:
        print("No se encontraron clientes")
    
    # Probar Storage
    print("\n3. Probando Firebase Storage...")
    bucket = firebase_service.get_storage_bucket()
    print(f"Storage Bucket: {bucket.name}")
    
    print("\n" + "=" * 50)
    print("¡Todo funciona correctamente!")
    print("=" * 50)
    
except Exception as e:
    print(f"\nError al conectar con Firebase:")
    print(f"   {str(e)}")
    print("\nVerifica:")
    print("   1. Que serviceAccountKey.json esté en la raíz del proyecto")
    print("   2. Que tu .env tenga las URLs correctas")
    print("   3. Que las credenciales sean válidas")