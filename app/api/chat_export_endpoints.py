"""
API endpoints for chat export functionality
"""

from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
import io
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors

from app.utils.decorators import admin_required
from app.models import Order, OrderChat, ChatMessage, User, db

bp = Blueprint('chat_export_api', __name__, url_prefix='/admin/chat')

@bp.route('/export/<int:order_id>', methods=['GET'])
@login_required
@admin_required
def export_order_chat(order_id):
    """Export chat messages for a specific order to PDF"""
    try:
        order = Order.query.get_or_404(order_id)
        chat = order.chat
        
        if not chat:
            return jsonify({'error': 'Чат для этого заказа не найден'}), 404
        
        # Get all messages
        messages = chat.messages.order_by(ChatMessage.created_at.asc()).all()
        
        # Create PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, 
                               topMargin=72, bottomMargin=18)
        
        # Get styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30,
            alignment=1  # Center alignment
        )
        
        # Story list for PDF content
        story = []
        
        # Title
        story.append(Paragraph(f"Чат по заказу №{order.generated_order_number}", title_style))
        story.append(Spacer(1, 12))
        
        # Order information
        order_info = [
            ['Заказ:', order.generated_order_number],
            ['Клиент:', f"{order.contact_first_name} {order.contact_last_name}"],
            ['Email:', order.contact_email],
            ['Телефон:', order.contact_phone or 'Не указан'],
            ['Сумма:', f"{order.total_amount} ₽"],
            ['Статус:', order.status],
            ['Дата создания:', order.created_at.strftime('%d.%m.%Y %H:%M')],
            ['Оператор:', order.operator.full_name if order.operator else 'Не назначен']
        ]
        
        order_table = Table(order_info, colWidths=[2*inch, 4*inch])
        order_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BACKGROUND', (1, 0), (1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(order_table)
        story.append(Spacer(1, 20))
        
        # Chat messages
        story.append(Paragraph("Переписка", styles['Heading2']))
        story.append(Spacer(1, 12))
        
        if not messages:
            story.append(Paragraph("Сообщений нет", styles['Normal']))
        else:
            for message in messages:
                # Message header
                message_time = message.created_at.strftime('%d.%m.%Y %H:%M:%S')
                sender_info = f"{message.sender.full_name} ({message.sender.role})"
                message_type = "Системное сообщение" if message.message_type == 'system' else "Пользователь"
                
                story.append(Paragraph(f"<b>{sender_info}</b> - {message_time} ({message_type})", styles['Normal']))
                story.append(Spacer(1, 6))
                
                # Message content
                message_text = message.message.replace('\n', '<br/>')
                story.append(Paragraph(message_text, styles['Normal']))
                
                # Attachment info
                if message.attachment_name:
                    story.append(Paragraph(f"<i>Прикреплен файл: {message.attachment_name}</i>", styles['Normal']))
                
                story.append(Spacer(1, 12))
        
        # Build PDF
        doc.build(story)
        
        # Get PDF content
        pdf_content = buffer.getvalue()
        buffer.close()
        
        # Create response
        response = current_app.response_class(
            pdf_content,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename=chat_order_{order.generated_order_number}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
            }
        )
        
        return response
        
    except Exception as e:
        current_app.logger.error(f'Chat export error: {str(e)}')
        return jsonify({'error': f'Ошибка экспорта чата: {str(e)}'}), 500

@bp.route('/export-all', methods=['GET'])
@login_required
@admin_required
def export_all_chats():
    """Export all chat messages to PDF"""
    try:
        # Get date range from query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Query orders with chats
        query = db.session.query(Order).join(OrderChat).distinct()
        
        if start_date:
            query = query.filter(Order.created_at >= datetime.strptime(start_date, '%Y-%m-%d'))
        if end_date:
            query = query.filter(Order.created_at <= datetime.strptime(end_date, '%Y-%m-%d'))
        
        orders = query.order_by(Order.created_at.desc()).all()
        
        # Create PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, 
                               topMargin=72, bottomMargin=18)
        
        # Get styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30,
            alignment=1
        )
        
        story = []
        
        # Title
        story.append(Paragraph("Экспорт всех чатов", title_style))
        story.append(Spacer(1, 12))
        
        # Date range info
        if start_date or end_date:
            date_info = "Период: "
            if start_date:
                date_info += f"с {start_date}"
            if end_date:
                date_info += f" по {end_date}"
            story.append(Paragraph(date_info, styles['Normal']))
            story.append(Spacer(1, 12))
        
        # Process each order
        for order in orders:
            chat = order.chat
            if not chat:
                continue
            
            messages = chat.messages.order_by(ChatMessage.created_at.asc()).all()
            
            # Order header
            story.append(Paragraph(f"Заказ №{order.generated_order_number}", styles['Heading2']))
            story.append(Spacer(1, 6))
            
            # Order summary
            order_summary = f"Клиент: {order.contact_first_name} {order.contact_last_name} | " \
                           f"Email: {order.contact_email} | " \
                           f"Сумма: {order.total_amount} ₽ | " \
                           f"Статус: {order.status} | " \
                           f"Сообщений: {len(messages)}"
            
            story.append(Paragraph(order_summary, styles['Normal']))
            story.append(Spacer(1, 12))
            
            # Messages
            if messages:
                for message in messages:
                    message_time = message.created_at.strftime('%d.%m.%Y %H:%M')
                    sender_info = f"{message.sender.full_name} ({message.sender.role})"
                    message_type = "Системное" if message.message_type == 'system' else "Пользователь"
                    
                    story.append(Paragraph(f"<b>{sender_info}</b> - {message_time} ({message_type})", styles['Normal']))
                    story.append(Spacer(1, 4))
                    
                    message_text = message.message.replace('\n', '<br/>')
                    story.append(Paragraph(message_text, styles['Normal']))
                    
                    if message.attachment_name:
                        story.append(Paragraph(f"<i>Файл: {message.attachment_name}</i>", styles['Normal']))
                    
                    story.append(Spacer(1, 8))
            else:
                story.append(Paragraph("Сообщений нет", styles['Normal']))
            
            story.append(Spacer(1, 20))
        
        # Build PDF
        doc.build(story)
        
        # Get PDF content
        pdf_content = buffer.getvalue()
        buffer.close()
        
        # Create response
        filename = f"all_chats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        if start_date or end_date:
            filename = f"chats_{start_date or 'all'}_{end_date or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        response = current_app.response_class(
            pdf_content,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename={filename}'
            }
        )
        
        return response
        
    except Exception as e:
        current_app.logger.error(f'All chats export error: {str(e)}')
        return jsonify({'error': f'Ошибка экспорта всех чатов: {str(e)}'}), 500

@bp.route('/statistics', methods=['GET'])
@login_required
@admin_required
def chat_statistics():
    """Get chat statistics"""
    try:
        # Total chats
        total_chats = OrderChat.query.count()
        
        # Total messages
        total_messages = ChatMessage.query.count()
        
        # Messages by type
        user_messages = ChatMessage.query.filter_by(message_type='user').count()
        system_messages = ChatMessage.query.filter_by(message_type='system').count()
        
        # Most active users
        active_users = db.session.query(
            User.full_name,
            User.role,
            db.func.count(ChatMessage.id).label('message_count')
        ).join(ChatMessage).filter(
            ChatMessage.message_type == 'user'
        ).group_by(User.id).order_by(
            db.func.count(ChatMessage.id).desc()
        ).limit(10).all()
        
        # Orders with most messages
        active_orders = db.session.query(
            Order.generated_order_number,
            db.func.count(ChatMessage.id).label('message_count')
        ).join(OrderChat).join(ChatMessage).group_by(
            Order.id
        ).order_by(
            db.func.count(ChatMessage.id).desc()
        ).limit(10).all()
        
        return jsonify({
            'success': True,
            'statistics': {
                'total_chats': total_chats,
                'total_messages': total_messages,
                'user_messages': user_messages,
                'system_messages': system_messages,
                'active_users': [
                    {
                        'name': user.full_name,
                        'role': user.role,
                        'message_count': user.message_count
                    }
                    for user in active_users
                ],
                'active_orders': [
                    {
                        'order_number': order.generated_order_number,
                        'message_count': order.message_count
                    }
                    for order in active_orders
                ]
            }
        })
        
    except Exception as e:
        current_app.logger.error(f'Chat statistics error: {str(e)}')
        return jsonify({'error': f'Ошибка получения статистики: {str(e)}'}), 500
