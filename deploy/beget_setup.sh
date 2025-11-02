#!/bin/bash
# MainStream Shop - Beget Server Setup Script

echo "🚀 Setting up MainStream Shop on Beget server..."

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11
sudo apt install software-properties-common -y
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev -y

# Install pip
curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11

# Install system dependencies
sudo apt install nginx supervisor git -y

# Create application directory (или используйте существующую ~/mainstreamfs.ru)
# sudo mkdir -p /opt/mainstreamshop
# sudo chown -R $USER:$USER /opt/mainstreamshop
# ИЛИ используйте:
cd ~/mainstreamfs.ru
# git clone https://github.com/AndryshaDenisov1488/mainstream-shop.git .

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Create necessary directories
mkdir -p uploads/xml logs backups

# Set permissions
chmod +x run.py
chmod 755 uploads logs

# Create systemd service (используйте файл mainstreamfs.service из репозитория)
# sudo cp ~/mainstreamfs.ru/mainstreamfs.service /etc/systemd/system/
# sudo systemctl daemon-reload
# sudo systemctl enable mainstreamfs

# Create Nginx configuration
sudo tee /etc/nginx/sites-available/mainstreamshop > /dev/null <<EOF
server {
    listen 80;
    server_name mainstreamfs.ru www.mainstreamfs.ru;
    
    # Redirect HTTP to HTTPS
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name mainstreamfs.ru www.mainstreamfs.ru;
    
    # SSL configuration (update paths to your certificates)
    ssl_certificate /etc/ssl/certs/mainstreamfs.ru.crt;
    ssl_certificate_key /etc/ssl/private/mainstreamfs.ru.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # Client max body size
    client_max_body_size 50M;
    
    # Static files
    location /static/ {
        alias /root/mainstreamfs.ru/app/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Uploads
    location /uploads/ {
        alias /root/mainstreamfs.ru/uploads/;
        expires 7d;
        add_header Cache-Control "public";
    }
    
    # Main application
    location / {
        proxy_pass http://127.0.0.1:5002;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Health check
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
EOF

# Enable Nginx site
sudo ln -sf /etc/nginx/sites-available/mainstreamshop /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
sudo nginx -t

# Create environment file
tee .env > /dev/null <<EOF
# Flask Configuration
FLASK_APP=run.py
FLASK_ENV=production
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')

# Database Configuration
DATABASE_URL=sqlite:///opt/mainstreamshop/app_prod.db

# Email Configuration
MAIL_SERVER=smtp.mail.ru
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=noreply@mainstreamfs.ru
MAIL_PASSWORD=your-mail-password
MAIL_DEFAULT_SENDER=MainStream Shop <noreply@mainstreamfs.ru>

# CloudPayments Configuration
CLOUDPAYMENTS_PUBLIC_ID=pk_46d0e6977b3b40502eba50d058c5f
CLOUDPAYMENTS_API_SECRET=f9c2be34714a135ac10efe57014b72cb

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your-telegram-bot-token

# Security Configuration
SESSION_COOKIE_SECURE=True
WTF_CSRF_ENABLED=True

# Server Configuration
PORT=5002
EOF

# Start services
sudo systemctl daemon-reload
sudo systemctl enable mainstreamshop
sudo systemctl start mainstreamshop

# Restart Nginx
sudo systemctl restart nginx

# Create backup script
tee backup.sh > /dev/null <<EOF
#!/bin/bash
# Backup script for MainStream Shop

BACKUP_DIR="/opt/mainstreamshop/backups"
DATE=\$(date +%Y%m%d_%H%M%S)
DB_FILE="/opt/mainstreamshop/app_prod.db"

# Create backup directory if it doesn't exist
mkdir -p \$BACKUP_DIR

# Backup database
if [ -f "\$DB_FILE" ]; then
    cp "\$DB_FILE" "\$BACKUP_DIR/app_\$DATE.db"
    echo "Database backed up to \$BACKUP_DIR/app_\$DATE.db"
fi

# Keep only last 7 days of backups
find \$BACKUP_DIR -name "app_*.db" -mtime +7 -delete

echo "Backup completed at \$(date)"
EOF

chmod +x backup.sh

# Create cron job for daily backups
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/mainstreamshop/backup.sh") | crontab -

echo "✅ MainStream Shop setup completed!"
echo ""
echo "📋 Next steps:"
echo "1. Update .env file with your actual email password and Telegram bot token"
echo "2. Upload your SSL certificates to /etc/ssl/certs/ and /etc/ssl/private/"
echo "3. Test the application: https://mainstreamfs.ru"
echo "4. Check logs: sudo journalctl -u mainstreamshop -f"
echo ""
echo "🔧 Useful commands:"
echo "  Start service: sudo systemctl start mainstreamshop"
echo "  Stop service: sudo systemctl stop mainstreamshop"
echo "  Restart service: sudo systemctl restart mainstreamshop"
echo "  View logs: sudo journalctl -u mainstreamshop -f"
echo "  Test Nginx: sudo nginx -t"
echo "  Reload Nginx: sudo systemctl reload nginx"
