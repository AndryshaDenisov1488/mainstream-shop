import re
from wtforms import ValidationError

try:
    import phonenumbers
    PHONENUMBERS_AVAILABLE = True
except ImportError:
    PHONENUMBERS_AVAILABLE = False

def validate_phone(form, field):
    """Validate Russian phone number"""
    if field.data and PHONENUMBERS_AVAILABLE:
        try:
            parsed_number = phonenumbers.parse(field.data, 'RU')
            if not phonenumbers.is_valid_number(parsed_number):
                raise ValidationError('Неверный формат номера телефона')
        except phonenumbers.NumberParseException:
            raise ValidationError('Неверный формат номера телефона')

def normalize_phone(phone_number):
    """Normalize phone number to E164 format"""
    if phone_number and PHONENUMBERS_AVAILABLE:
        try:
            parsed_number = phonenumbers.parse(phone_number, 'RU')
            return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            return phone_number
    return phone_number

def validate_email_domain(form, field):
    """Validate email domain"""
    if field.data:
        # Check for common disposable email domains
        disposable_domains = [
            '10minutemail.com', 'tempmail.org', 'guerrillamail.com',
            'mailinator.com', 'throwaway.email', 'temp-mail.org'
        ]
        
        domain = field.data.split('@')[1].lower()
        if domain in disposable_domains:
            raise ValidationError('Пожалуйста, используйте постоянный email адрес')

def sanitize_filename(filename):
    """Sanitize filename for safe upload"""
    # Remove path components
    filename = filename.split('/')[-1].split('\\')[-1]
    
    # Remove dangerous characters
    filename = re.sub(r'[^\w\-_\.]', '_', filename)
    
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1)
        filename = name[:250] + '.' + ext
    
    return filename

def validate_xml_content(content):
    """Validate XML content"""
    try:
        import xml.etree.ElementTree as ET
        ET.fromstring(content)
        return True
    except Exception:
        return False

def validate_file_extension(filename, allowed_extensions):
    """Validate file extension"""
    if '.' not in filename:
        return False
    
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in allowed_extensions

def validate_file_size(file, max_size_mb):
    """Validate file size"""
    file.seek(0, 2)  # Seek to end
    size = file.tell()
    file.seek(0)  # Reset position
    
    max_size_bytes = max_size_mb * 1024 * 1024
    return size <= max_size_bytes
