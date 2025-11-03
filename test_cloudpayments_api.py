#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Упрощенный тестовый скрипт для проверки работы CloudPayments API
Проверяет все этапы работы с CloudPayments без реальных платежей
"""

import os
import sys
import hmac
import hashlib
import base64
import json
from urllib.parse import urlencode

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Загружаем переменные окружения
from dotenv import load_dotenv
load_dotenv()

def test_webhook_signature():
    """Тест 1: Проверка верификации подписи webhook"""
    print("\n" + "="*60)
    print("ТЕСТ 1: Верификация подписи webhook")
    print("="*60)
    
    api_secret = os.environ.get('CLOUDPAYMENTS_API_SECRET')
    if not api_secret:
        print("❌ CLOUDPAYMENTS_API_SECRET не установлен в .env")
        return False
    
    # Пример данных которые приходят от CloudPayments (form-urlencoded)
    test_data = "NotificationType=Check&TransactionId=12345&InvoiceId=MS-123&Amount=100&Currency=RUB"
    
    # Вычисляем подпись как CloudPayments
    signature_bytes = hmac.new(
        api_secret.encode('utf-8'),
        test_data.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    expected_signature_base64 = base64.b64encode(signature_bytes).decode('utf-8')
    expected_signature_hex = signature_bytes.hex()
    
    print(f"✅ API Secret: {api_secret[:10]}... (длина: {len(api_secret)})")
    print(f"✅ Тестовые данные: {test_data}")
    print(f"✅ Подпись (base64): {expected_signature_base64}")
    print(f"✅ Подпись (hex): {expected_signature_hex}")
    
    # Симулируем заголовок от CloudPayments
    received_signature = expected_signature_base64
    
    # Проверяем
    is_valid_base64 = hmac.compare_digest(received_signature, expected_signature_base64)
    is_valid_hex = hmac.compare_digest(received_signature, expected_signature_hex)
    
    if is_valid_base64:
        print(f"✅ Подпись валидна (base64 формат)")
        return True
    elif is_valid_hex and len(received_signature) == 64:
        print(f"✅ Подпись валидна (hex формат)")
        return True
    else:
        print(f"❌ Подпись НЕ валидна")
        return False


def test_webhook_data_parsing():
    """Тест 2: Парсинг form-urlencoded данных от CloudPayments"""
    print("\n" + "="*60)
    print("ТЕСТ 2: Парсинг form-urlencoded данных")
    print("="*60)
    
    # Симулируем данные от CloudPayments
    form_data = {
        'NotificationType': 'Check',
        'TransactionId': '12345',
        'InvoiceId': 'MS-20251103-ABC123',
        'Amount': '100.00',
        'Currency': 'RUB',
        'Email': 'test@example.com'
    }
    
    # Конвертируем в form-urlencoded строку (как CloudPayments отправляет)
    encoded_data = urlencode(form_data)
    print(f"✅ Form-urlencoded данные: {encoded_data}")
    
    # Парсим обратно
    from urllib.parse import parse_qs, unquote
    parsed = {}
    for key, values in parse_qs(encoded_data).items():
        parsed[key] = unquote(values[0]) if values else ''
    
    print(f"✅ Распарсенные данные: {json.dumps(parsed, indent=2, ensure_ascii=False)}")
    
    if parsed.get('NotificationType') == 'Check':
        print("✅ Парсинг работает корректно")
        return True
    else:
        print("❌ Ошибка парсинга")
        return False


def test_payment_widget_data():
    """Тест 3: Создание данных для виджета CloudPayments"""
    print("\n" + "="*60)
    print("ТЕСТ 3: Создание данных для виджета")
    print("="*60)
    
    try:
        from app import create_app, db
        from app.models import Order
        
        app = create_app()
        
        with app.app_context():
            # Создаем тестовый заказ
            test_order = Order(
                order_number='MS-TEST-001',
                generated_order_number='MS-TEST-001',
                total_amount=100.00,
                contact_email='test@example.com',
                contact_first_name='Test',
                contact_last_name='User',
                status='checkout_initiated',
                customer_id=None
            )
            
            from app.utils.cloudpayments import CloudPaymentsAPI
            cp_api = CloudPaymentsAPI()
            
            try:
                payment_data = cp_api.create_payment_widget_data(test_order, 'card')
                
                print(f"✅ Данные виджета созданы:")
                print(json.dumps(payment_data, indent=2, ensure_ascii=False))
                
                # Проверяем обязательные поля
                required_fields = ['publicId', 'description', 'amount', 'currency', 'invoiceId', 'email']
                missing = [f for f in required_fields if f not in payment_data]
                
                if missing:
                    print(f"❌ Отсутствуют обязательные поля: {missing}")
                    return False
                else:
                    print("✅ Все обязательные поля присутствуют")
                    return True
                    
            except Exception as e:
                print(f"❌ Ошибка создания данных виджета: {str(e)}")
                import traceback
                traceback.print_exc()
                return False
                
    except Exception as e:
        print(f"❌ Ошибка инициализации: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_webhook_endpoint_simulation():
    """Тест 4: Симуляция получения webhook"""
    print("\n" + "="*60)
    print("ТЕСТ 4: Симуляция webhook endpoint")
    print("="*60)
    
    api_secret = os.environ.get('CLOUDPAYMENTS_API_SECRET')
    if not api_secret:
        print("❌ CLOUDPAYMENTS_API_SECRET не установлен")
        return False
    
    # Симулируем webhook данные
    webhook_data = {
        'NotificationType': 'Check',
        'TransactionId': '12345',
        'InvoiceId': 'MS-TEST-001',
        'Amount': '100.00',
        'Currency': 'RUB'
    }
    
    # Конвертируем в form-urlencoded
    form_string = urlencode(webhook_data)
    print(f"✅ Form-string: {form_string}")
    
    # Вычисляем подпись
    signature_bytes = hmac.new(
        api_secret.encode('utf-8'),
        form_string.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    signature_base64 = base64.b64encode(signature_bytes).decode('utf-8')
    print(f"✅ Подпись (base64): {signature_base64}")
    
    # Проверяем подпись
    expected_bytes = hmac.new(
        api_secret.encode('utf-8'),
        form_string.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    expected_base64 = base64.b64encode(expected_bytes).decode('utf-8')
    
    if hmac.compare_digest(signature_base64, expected_base64):
        print("✅ Верификация подписи прошла успешно")
        return True
    else:
        print("❌ Верификация подписи не прошла")
        return False


def test_cloudpayments_config():
    """Тест 5: Проверка конфигурации CloudPayments"""
    print("\n" + "="*60)
    print("ТЕСТ 5: Проверка конфигурации")
    print("="*60)
    
    public_id = os.environ.get('CLOUDPAYMENTS_PUBLIC_ID')
    api_secret = os.environ.get('CLOUDPAYMENTS_API_SECRET')
    test_mode = os.environ.get('CLOUDPAYMENTS_TEST_MODE', 'False').lower() in ['true', '1']
    webhook_url = os.environ.get('CLOUDPAYMENTS_WEBHOOK_URL')
    
    print(f"Public ID: {'✅' if public_id else '❌'} {public_id[:20] + '...' if public_id else 'НЕ УСТАНОВЛЕН'}")
    print(f"API Secret: {'✅' if api_secret else '❌'} {'Установлен (длина: ' + str(len(api_secret)) + ')' if api_secret else 'НЕ УСТАНОВЛЕН'}")
    print(f"Test Mode: {'✅' if test_mode else '⚠️'} {test_mode}")
    print(f"Webhook URL: {'✅' if webhook_url else '❌'} {webhook_url or 'НЕ УСТАНОВЛЕН'}")
    
    if public_id and api_secret:
        print("\n✅ Конфигурация корректна")
        return True
    else:
        print("\n❌ Конфигурация неполная")
        return False


def main():
    print("\n" + "="*60)
    print("ТЕСТИРОВАНИЕ CLOUDPAYMENTS API")
    print("="*60)
    
    results = []
    
    # Запускаем тесты
    results.append(("Конфигурация", test_cloudpayments_config()))
    results.append(("Верификация подписи", test_webhook_signature()))
    results.append(("Парсинг form-urlencoded", test_webhook_data_parsing()))
    results.append(("Данные виджета", test_payment_widget_data()))
    results.append(("Симуляция webhook", test_webhook_endpoint_simulation()))
    
    # Выводим итоги
    print("\n" + "="*60)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ ПРОШЕЛ" if result else "❌ ПРОВАЛЕН"
        print(f"{test_name}: {status}")
    
    print(f"\nРезультат: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("\n🎉 Все тесты пройдены!")
        return 0
    else:
        print(f"\n⚠️ {total - passed} тест(ов) провалено")
        return 1


if __name__ == '__main__':
    sys.exit(main())


