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
    """
    Normalize phone number to E164 format (+7XXXXXXXXXX)
    Supports formats:
    - 89060943936 -> +79060943936
    - 79060943936 -> +79060943936
    - +79060943936 -> +79060943936
    - 9060943936 -> +79060943936
    """
    if not phone_number:
        return None
    
    # Remove all non-digit characters except +
    cleaned = re.sub(r'[^\d+]', '', str(phone_number).strip())
    
    if PHONENUMBERS_AVAILABLE:
        try:
            # Try to parse and format
            parsed_number = phonenumbers.parse(cleaned, 'RU')
            if phonenumbers.is_valid_number(parsed_number):
                return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            pass
    
    # Fallback: manual normalization for Russian numbers
    # Remove + if present
    digits_only = cleaned.replace('+', '')
    
    # Handle different formats
    if digits_only.startswith('8') and len(digits_only) == 11:
        # 89060943936 -> 79060943936
        digits_only = '7' + digits_only[1:]
    elif digits_only.startswith('7') and len(digits_only) == 11:
        # 79060943936 -> already correct
        pass
    elif len(digits_only) == 10:
        # 9060943936 -> 79060943936
        digits_only = '7' + digits_only
    elif not digits_only.startswith('7'):
        # If doesn't start with 7 or 8, try adding 7
        if len(digits_only) == 10:
            digits_only = '7' + digits_only
        elif len(digits_only) == 11 and digits_only.startswith('8'):
            digits_only = '7' + digits_only[1:]
    
    # Return in E164 format
    if digits_only.startswith('7') and len(digits_only) == 11:
        return '+' + digits_only
    
    # If we can't normalize, return original (will be validated elsewhere)
    return phone_number.strip() if phone_number else None

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
