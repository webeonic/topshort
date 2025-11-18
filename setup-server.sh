#!/bin/bash

# TopShort - Server Setup Script for Digital Ocean
# Run this script on a fresh Ubuntu 22.04 Droplet

set -e

echo "=========================================="
echo "TopShort Trading Bot - Server Setup"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (use: sudo -i)"
    exit 1
fi

# Update system
echo "📦 Updating system packages..."
apt update && apt upgrade -y

# Install Docker
echo "🐳 Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    echo "✅ Docker installed"
else
    echo "✅ Docker already installed"
fi

# Install Docker Compose
echo "🐳 Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    apt install docker-compose -y
    echo "✅ Docker Compose installed"
else
    echo "✅ Docker Compose already installed"
fi

# Install Git
echo "📥 Installing Git..."
if ! command -v git &> /dev/null; then
    apt install git -y
    echo "✅ Git installed"
else
    echo "✅ Git already installed"
fi

# Create deployer user (optional)
echo ""
read -p "Create deployer user for security? (recommended) [y/N]: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if id "deployer" &>/dev/null; then
        echo "✅ User 'deployer' already exists"
    else
        echo "👤 Creating deployer user..."
        adduser --disabled-password --gecos "" deployer
        usermod -aG sudo deployer
        usermod -aG docker deployer

        # Setup SSH for deployer
        mkdir -p /home/deployer/.ssh
        if [ -f /root/.ssh/authorized_keys ]; then
            cp /root/.ssh/authorized_keys /home/deployer/.ssh/
            chown -R deployer:deployer /home/deployer/.ssh
            chmod 700 /home/deployer/.ssh
            chmod 600 /home/deployer/.ssh/authorized_keys
            echo "✅ SSH keys copied to deployer user"
        fi
        echo "✅ Deployer user created"
    fi
fi

# Create project directory
echo ""
echo "📁 Creating project directory..."
mkdir -p /opt/topshort
cd /opt/topshort

# Clone repository
echo ""
read -p "Enter GitHub repository URL (https://github.com/webeonic/topshort.git): " REPO_URL
REPO_URL=${REPO_URL:-https://github.com/webeonic/topshort.git}

if [ -d "/opt/topshort/.git" ]; then
    echo "✅ Repository already cloned"
else
    git clone "$REPO_URL" .
    echo "✅ Repository cloned"
fi

# Setup .env file
echo ""
echo "⚙️  Setting up environment file..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "❗ IMPORTANT: Edit /opt/topshort/.env with your API keys"
    echo "   Run: nano /opt/topshort/.env"
else
    echo "✅ .env file already exists"
fi

# Setup firewall
echo ""
read -p "Setup UFW firewall? (recommended) [y/N]: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🔥 Setting up firewall..."
    apt install ufw -y
    ufw --force enable
    ufw allow 22/tcp
    echo "✅ Firewall configured (SSH allowed)"
fi

# Setup automatic backups
echo ""
read -p "Setup automatic database backups? [y/N]: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "💾 Setting up backup script..."
    mkdir -p /opt/topshort/backups

    cat > /opt/topshort/backup.sh << 'BACKUP_SCRIPT'
#!/bin/bash
BACKUP_DIR="/opt/topshort/backups"
mkdir -p $BACKUP_DIR
DATE=$(date +%Y%m%d_%H%M%S)
cp /opt/topshort/data/topshort.db $BACKUP_DIR/backup_$DATE.db 2>/dev/null || true
find $BACKUP_DIR -name "backup_*.db" -mtime +7 -delete
BACKUP_SCRIPT

    chmod +x /opt/topshort/backup.sh

    # Add to crontab
    (crontab -l 2>/dev/null; echo "0 3 * * * /opt/topshort/backup.sh") | crontab -
    echo "✅ Backup script created (runs daily at 3:00 AM)"
fi

# Create GitHub Actions SSH key
echo ""
read -p "Generate SSH key for GitHub Actions CI/CD? [y/N]: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🔑 Generating SSH key for GitHub Actions..."
    ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_actions_key -N "" >/dev/null 2>&1 || true
    cat ~/.ssh/github_actions_key.pub >> ~/.ssh/authorized_keys

    echo ""
    echo "=========================================="
    echo "GitHub Actions SSH Setup"
    echo "=========================================="
    echo ""
    echo "Add these secrets to your GitHub repository:"
    echo "(Settings → Secrets and variables → Actions)"
    echo ""
    echo "1. DO_SSH_PRIVATE_KEY:"
    echo "---"
    cat ~/.ssh/github_actions_key
    echo "---"
    echo ""
    echo "2. DO_HOST:"
    echo "$(curl -s ifconfig.me)"
    echo ""
    echo "3. DO_USER:"
    echo "root"
    echo ""
    echo "=========================================="
    echo ""
    read -p "Press Enter when you've added the secrets..."
fi

# Test Docker
echo ""
echo "🧪 Testing Docker installation..."
docker run --rm hello-world > /dev/null 2>&1 && echo "✅ Docker working correctly"

echo ""
echo "=========================================="
echo "✅ Server Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit environment file: nano /opt/topshort/.env"
echo "2. Build and start bot: cd /opt/topshort && docker-compose up -d"
echo "3. View logs: docker-compose logs -f"
echo "4. Check status via Telegram: /status"
echo ""
echo "Useful commands:"
echo "  cd /opt/topshort          - Go to project directory"
echo "  docker-compose logs -f    - View logs"
echo "  docker-compose restart    - Restart bot"
echo "  docker-compose ps         - Check status"
echo ""
echo "Documentation:"
echo "  README.md      - Full documentation"
echo "  DEPLOYMENT.md  - Deployment guide"
echo "  QUICKSTART.md  - Quick start guide"
echo ""
echo "Happy trading! 🚀"
