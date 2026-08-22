#!/usr/bin/env bash
# ==============================================================================
# DARSI Backend — Cloudflare Zero Trust Tunnel Setup Script (ADR-027)
#
# Script ini mengotomatiskan instalasi dan konfigurasi daemon Cloudflare Tunnel
# di server Linux (Ubuntu/Debian/CentOS) yang berada di balik private network / VPN.
# ==============================================================================

set -e

echo "======================================================"
echo "  DARSI Backend — Cloudflare Tunnel Ingress Setup     "
echo "======================================================"

# 1. Deteksi & Instalasi cloudflared
if ! command -v cloudflared &> /dev/null; then
    echo "[1/4] Menginstal cloudflared..."
    ARCH=$(dpkg --print-architecture 2>/dev/null || echo "amd64")
    curl -fsSL -o cloudflared.deb "https://github.com/cloudflare/cloudflare-tunnel-remote/releases/latest/download/cloudflared-linux-${ARCH}.deb" || \
    curl -fsSL -o cloudflared.deb "https://pkg.cloudflare.com/cloudflared-ascii/cloudflared-linux-${ARCH}.deb"
    
    sudo dpkg -i cloudflared.deb || sudo apt-get install -f -y
    rm -f cloudflared.deb
    echo "[✓] cloudflared berhasil diinstal."
else
    echo "[✓] cloudflared sudah terinstal."
fi

cloudflared --version

echo ""
echo "[2/4] Pilih mode Ingress yang ingin dijalankan:"
echo "------------------------------------------------------"
echo "1. Quick Tunnel (Gratis, tanpa login/domain, URL sementara: https://xxxx.trycloudflare.com)"
echo "2. Production Named Tunnel (Terhubung ke Cloudflare Dashboard / Custom Domain)"
echo "------------------------------------------------------"
read -p "Pilihan Anda (1/2): " choice

case $choice in
    1)
        echo ""
        echo "[3/4] Menjalankan Quick Tunnel ke http://localhost:8000..."
        echo "Tunggu beberapa detik hingga URL *.trycloudflare.com muncul di layar."
        echo "Salin URL tersebut dan masukkan ke AssistantClient.cs di Unity."
        echo "Tekan Ctrl+C untuk menghentikan tunnel."
        echo "------------------------------------------------------"
        cloudflared tunnel --url http://localhost:8000
        ;;
    2)
        echo ""
        echo "[3/4] Konfigurasi Production Named Tunnel:"
        echo "Langkah 1: Login ke Cloudflare (buka link browser yang muncul):"
        cloudflared tunnel login
        
        read -p "Masukkan nama tunnel (default: darsi-api): " TUNNEL_NAME
        TUNNEL_NAME=${TUNNEL_NAME:-darsi-api}
        
        echo "Langkah 2: Membuat tunnel '$TUNNEL_NAME'..."
        cloudflared tunnel create "$TUNNEL_NAME"
        
        read -p "Masukkan domain/subdomain resmi (contoh: api.darsi.id): " DOMAIN_NAME
        
        echo "Langkah 3: Mendaftarkan DNS route..."
        cloudflared tunnel route dns "$TUNNEL_NAME" "$DOMAIN_NAME"
        
        echo "Langkah 4: Menginstal tunnel sebagai system service (systemd)..."
        sudo cloudflared service install
        sudo systemctl start cloudflared
        sudo systemctl enable cloudflared
        
        echo ""
        echo "[✓] Setup Production Selesai!"
        echo "Endpoint publik Anda: https://$DOMAIN_NAME"
        ;;
    *)
        echo "Pilihan tidak valid. Keluar."
        exit 1
        ;;
esac
