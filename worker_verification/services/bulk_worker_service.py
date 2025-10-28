import pandas as pd
import secrets
import string
from datetime import datetime
from firebase_admin import auth
from .firebase_service import firebase_service
import logging

logger = logging.getLogger(__name__)


class BulkWorkerUploadService:
    """
    Servicio para carga masiva de trabajadores desde Excel
    """
    
    WORKERS_PATH = 'User/Trabajadores'
    
    # Mapeo de columnas Excel a campos del modelo
    EXCEL_COLUMN_MAPPING = {
        'nombre': 'name',
        'apellido': 'lastName',
        'email': 'email',
        'telefono': 'phone',
        'categoria': 'work',
        'descripcion': 'description',
        'latitud': 'latitude',
        'longitud': 'longitude',
        'precio_por_hora': 'pricePerHour',
        'experiencia': 'experience',
        'contraseña': 'password',  # Opcional
    }
    
    def __init__(self):
        self.firebase = firebase_service
    
    def generate_secure_password(self, length=12):
        """
        Genera una contraseña segura aleatoria
        """
        alphabet = string.ascii_letters + string.digits + "!@#$%&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        
        # Asegurar que tenga al menos una mayúscula, minúscula, número y símbolo
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%&*" for c in password)
        
        if not (has_upper and has_lower and has_digit and has_special):
            return self.generate_secure_password(length)
        
        return password
    
    def get_current_timestamp_millis(self):
        """
        ✅ CRÍTICO: Retorna timestamp en MILISEGUNDOS (compatible con Android Long)
        """
        return int(datetime.now().timestamp() * 1000)
    
    def validate_excel_structure(self, df):
        """
        Valida que el Excel tenga las columnas requeridas
        """
        required_columns = ['nombre', 'apellido', 'email', 'telefono', 'categoria']
        
        # Normalizar nombres de columnas
        df.columns = df.columns.str.lower().str.strip().str.replace(' ', '_')
        
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            raise ValueError(f"Columnas faltantes en el Excel: {', '.join(missing_columns)}")
        
        return df
    
    def parse_excel_row(self, row):
        """
        Convierte una fila del Excel al formato del modelo
        """
        worker_data = {}
        
        for excel_col, model_field in self.EXCEL_COLUMN_MAPPING.items():
            if excel_col in row.index:
                value = row[excel_col]
                
                # Manejar valores NaN
                if pd.isna(value):
                    if excel_col in ['descripcion', 'experiencia', 'contraseña']:
                        worker_data[model_field] = ''
                    elif excel_col in ['latitud', 'longitud', 'precio_por_hora']:
                        worker_data[model_field] = 0.0
                    elif excel_col == 'telefono':
                        worker_data[model_field] = ''
                else:
                    # ✅ CRÍTICO: Convertir teléfono a STRING (Android espera String)
                    if excel_col == 'telefono':
                        # Remover decimales si pandas lo convirtió a float
                        if isinstance(value, (int, float)):
                            worker_data[model_field] = str(int(value))
                        else:
                            worker_data[model_field] = str(value).strip()
                    else:
                        worker_data[model_field] = value
        
        # Valores por defecto
        worker_data.setdefault('isAvailable', False)  # FALSE hasta completar documentos
        worker_data.setdefault('isOnline', False)
        worker_data.setdefault('rating', 0.0)
        worker_data.setdefault('totalRatings', 0)
        worker_data.setdefault('phone', '')  # ✅ Asegurar que phone sea string vacío si no existe
        
        # ✅ CORREGIDO: timestamp como LONG (milisegundos) para compatibilidad con Android
        worker_data.setdefault('timestamp', self.get_current_timestamp_millis())
        
        return worker_data
    
    def create_firebase_auth_user(self, email, password, display_name):
        """
        Crea un usuario en Firebase Authentication
        
        Returns:
            tuple: (user_id, password_used, error)
        """
        try:
            # Generar contraseña si no se proporcionó
            if not password or password.strip() == '':
                password = self.generate_secure_password()
            
            # Crear usuario en Firebase Auth
            user = auth.create_user(
                email=email,
                password=password,
                display_name=display_name,
                email_verified=False  # Requerirá verificación
            )
            
            logger.info(f"Firebase Auth user created: {user.uid} - {email}")
            return user.uid, password, None
            
        except auth.EmailAlreadyExistsError:
            # Si el usuario ya existe, obtener su UID
            try:
                existing_user = auth.get_user_by_email(email)
                logger.warning(f"User already exists in Auth: {email}")
                return existing_user.uid, None, "Usuario ya existe en Firebase Auth"
            except Exception as e:
                return None, None, f"Error verificando usuario existente: {str(e)}"
                
        except Exception as e:
            logger.error(f"Error creating Firebase Auth user: {str(e)}")
            return None, None, str(e)
    
    def create_worker_profile(self, user_id, worker_data):
        """
        Crea el perfil del trabajador en Realtime Database
        """
        try:
            # Remover contraseña del perfil (no se guarda en DB)
            if 'password' in worker_data:
                del worker_data['password']
            
            # Agregar ID
            worker_data['id'] = user_id
            
            # ✅ IMPORTANTE: Asegurar que todos los campos NUMÉRICOS sean del tipo correcto
            # Convertir explícitamente a tipos nativos de Python (no numpy)
            if 'latitude' in worker_data:
                worker_data['latitude'] = float(worker_data['latitude'])
            if 'longitude' in worker_data:
                worker_data['longitude'] = float(worker_data['longitude'])
            if 'pricePerHour' in worker_data:
                worker_data['pricePerHour'] = float(worker_data['pricePerHour'])
            if 'rating' in worker_data:
                worker_data['rating'] = float(worker_data['rating'])
            if 'totalRatings' in worker_data:
                worker_data['totalRatings'] = int(worker_data['totalRatings'])
            
            # ✅ CRÍTICO: Asegurar que campos STRING sean realmente strings
            string_fields = ['name', 'lastName', 'email', 'phone', 'work', 'description', 'experience']
            for field in string_fields:
                if field in worker_data:
                    # Convertir a string y limpiar
                    if pd.isna(worker_data[field]) or worker_data[field] is None:
                        worker_data[field] = ''
                    else:
                        worker_data[field] = str(worker_data[field]).strip()
            
            # ✅ CRÍTICO: Asegurar que timestamp sea LONG (milisegundos)
            if 'timestamp' not in worker_data or isinstance(worker_data['timestamp'], str):
                worker_data['timestamp'] = self.get_current_timestamp_millis()
            else:
                # Si viene de Excel, asegurar que sea int
                worker_data['timestamp'] = int(worker_data['timestamp'])
            
            # ✅ Asegurar que booleanos sean realmente boolean
            worker_data['isAvailable'] = bool(worker_data.get('isAvailable', False))
            worker_data['isOnline'] = bool(worker_data.get('isOnline', False))
            
            # Crear en Firebase
            path = f"{self.WORKERS_PATH}/{user_id}"
            self.firebase.set_data(path, worker_data)
            
            logger.info(f"Worker profile created: {user_id}")
            return True, None
            
        except Exception as e:
            logger.error(f"Error creating worker profile: {str(e)}")
            return False, str(e)
    
    def process_excel_file(self, excel_file):
        """
        Procesa el archivo Excel y crea los trabajadores
        
        Returns:
            dict: Resultado del procesamiento
        """
        start_time = datetime.now()
        
        results = {
            'total_processed': 0,
            'successful': 0,
            'failed': 0,
            'success_details': [],
            'error_details': [],
            'execution_time': 0.0
        }
        
        try:
            # Leer Excel
            df = pd.read_excel(excel_file)
            
            # Validar estructura
            df = self.validate_excel_structure(df)
            
            results['total_processed'] = len(df)
            
            # Procesar cada fila
            for index, row in df.iterrows():
                row_number = index + 2  # +2 porque Excel empieza en 1 y hay header
                
                try:
                    # Parsear datos
                    worker_data = self.parse_excel_row(row)
                    
                    email = worker_data.get('email')
                    name = worker_data.get('name', '')
                    lastName = worker_data.get('lastName', '')
                    display_name = f"{name} {lastName}".strip()
                    password = worker_data.get('password', '')
                    
                    # Crear usuario en Firebase Auth
                    user_id, password_used, auth_error = self.create_firebase_auth_user(
                        email, password, display_name
                    )
                    
                    if not user_id:
                        results['failed'] += 1
                        results['error_details'].append({
                            'row': row_number,
                            'email': email,
                            'name': display_name,
                            'error': f"Error en Auth: {auth_error}"
                        })
                        continue
                    
                    # Crear perfil en Database
                    success, profile_error = self.create_worker_profile(user_id, worker_data)
                    
                    if success:
                        results['successful'] += 1
                        results['success_details'].append({
                            'row': row_number,
                            'email': email,
                            'name': display_name,
                            'user_id': user_id,
                            'password': password_used,  # Para enviar al usuario
                            'auth_existed': auth_error is not None
                        })
                    else:
                        results['failed'] += 1
                        results['error_details'].append({
                            'row': row_number,
                            'email': email,
                            'name': display_name,
                            'error': f"Error creando perfil: {profile_error}"
                        })
                        
                        # Intentar eliminar usuario de Auth si falló el perfil
                        try:
                            auth.delete_user(user_id)
                            logger.info(f"Rolled back Auth user: {user_id}")
                        except:
                            pass
                    
                except Exception as e:
                    results['failed'] += 1
                    results['error_details'].append({
                        'row': row_number,
                        'email': row.get('email', 'N/A'),
                        'name': f"{row.get('nombre', '')} {row.get('apellido', '')}",
                        'error': str(e)
                    })
            
            # Calcular tiempo de ejecución
            end_time = datetime.now()
            results['execution_time'] = (end_time - start_time).total_seconds()
            
            logger.info(f"Bulk upload completed: {results['successful']} successful, {results['failed']} failed")
            return results
            
        except Exception as e:
            logger.error(f"Error processing Excel file: {str(e)}")
            raise
    
    def generate_excel_template(self):
        """
        Genera un template de Excel con ejemplos
        """
        template_data = {
            'nombre': ['Juan', 'María', 'Pedro'],
            'apellido': ['Pérez', 'García', 'López'],
            'email': ['juan.perez@example.com', 'maria.garcia@example.com', 'pedro.lopez@example.com'],
            'telefono': ['3001234567', '3109876543', '3157654321'],
            'categoria': ['Electricista', 'Plomero', 'Carpintero'],
            'descripcion': ['Electricista con 10 años de experiencia', '', 'Carpintero especializado en muebles'],
            'latitud': [4.7110, 0.0, 4.6097],
            'longitud': [-74.0721, 0.0, -74.0817],
            'precio_por_hora': [50000, 45000, 60000],
            'experiencia': ['10 años', '5 años', '8 años'],
            'contraseña': ['', '', ''],  # Opcional - se autogenera si está vacío
        }
        
        df = pd.DataFrame(template_data)
        return df


# Instancia global del servicio
bulk_worker_service = BulkWorkerUploadService()