# HTTP MCP Transport Guide for ActiveDirectoryMCP

Bu rehber, ActiveDirectoryMCP sunucusunu HTTP transport ile nasıl kullanacağınızı açıklar.

## 🚀 Hızlı Başlangıç

### Docker Compose ile (Önerilen)

```bash
# Projeyi klonlayın
git clone https://github.com/alpadalar/ActiveDirectoryMCP.git
cd ActiveDirectoryMCP

# Konfigürasyonu ayarlayın
cp ad-config/config.example.json ad-config/config.json
# config.json dosyasını kendi AD ayarlarınızla düzenleyin

# Docker Compose ile başlatın
docker compose up -d

# HTTP endpoint: http://localhost:8813/activedirectory-mcp
```

### Manuel HTTP Server

```bash
# Sanal ortamı hazırlayın
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# HTTP sunucusunu başlatın
./start_http_server.sh

# Veya özelleştirilmiş ayarlarla
python -m active_directory_mcp.server_http --host 0.0.0.0 --port 8813 --path /activedirectory-mcp
```

## 🔧 Cursor/VS Code Entegrasyonu

### Option 1: Docker Compose HTTP Transport (Önerilen)

`~/.cursor/mcp_settings.json` veya VS Code MCP ayarlarınıza ekleyin:

```json
{
    "mcpServers": {
        "ActiveDirectoryMCP": {
            "transport": {
                "type": "http",
                "url": "http://localhost:8813/activedirectory-mcp"
            },
            "description": "Active Directory Management with HTTP Transport"
        }
    }
}
```

### Option 2: Lokal HTTP Server

```json
{
    "mcpServers": {
        "ActiveDirectoryMCP-Local": {
            "transport": {
                "type": "http", 
                "url": "http://localhost:8813/activedirectory-mcp"
            },
            "description": "ActiveDirectoryMCP Local Development"
        }
    }
}
```

### Option 3: Traditional Stdio Transport

```json
{
    "mcpServers": {
        "ActiveDirectoryMCP-Stdio": {
            "command": "/absolute/path/to/ActiveDirectoryMCP/.venv/bin/python",
            "args": ["-m", "active_directory_mcp.server"],
            "cwd": "/absolute/path/to/ActiveDirectoryMCP",
            "env": {
                "PYTHONPATH": "/absolute/path/to/ActiveDirectoryMCP/src",
                "AD_MCP_CONFIG": "/absolute/path/to/ActiveDirectoryMCP/ad-config/config.json"
            },
            "disabled": false
        }
    }
}
```

## 📋 Mevcut Tool'lar

### 👥 Kullanıcı Yönetimi
- `list_users` - Kullanıcıları listele ve filtrele
- `get_user` - Belirli bir kullanıcının detay bilgilerini al
- `create_user` - Yeni kullanıcı hesabı oluştur
- `modify_user` - Kullanıcı bilgilerini güncelle
- `delete_user` - Kullanıcı hesabını sil
- `enable_user` / `disable_user` - Hesap durumunu yönet
- `reset_user_password` - Şifre sıfırlama
- `get_user_groups` - Kullanıcının üye olduğu grupları listele

### 🔐 Grup Yönetimi  
- `list_groups` - Grupları listele
- `get_group` - Grup detaylarını al
- `create_group` - Yeni güvenlik/dağıtım grubu oluştur
- `modify_group` - Grup özelliklerini güncelle
- `delete_group` - Grup sil
- `add_group_member` / `remove_group_member` - Üyelik yönetimi
- `get_group_members` - Grup üyelerini listele

### 💻 Bilgisayar Yönetimi
- `list_computers` - Bilgisayar hesaplarını listele
- `get_computer` - Bilgisayar detaylarını al
- `create_computer` - Yeni bilgisayar nesnesi oluştur
- `modify_computer` - Bilgisayar özelliklerini güncelle
- `delete_computer` - Bilgisayar hesabını sil
- `enable_computer` / `disable_computer` - Hesap durumu yönetimi
- `reset_computer_password` - Bilgisayar şifresini sıfırla
- `get_stale_computers` - Aktif olmayan bilgisayarları tespit et

### 🏢 Organizasyon Birimi Yönetimi
- `list_organizational_units` - OU'ları listele
- `get_organizational_unit` - OU detaylarını al
- `create_organizational_unit` - Yeni OU oluştur
- `modify_organizational_unit` - OU özelliklerini güncelle
- `delete_organizational_unit` - OU sil
- `move_organizational_unit` - OU'yu taşı
- `get_organizational_unit_contents` - OU içeriğini listele

### 🛡️ Güvenlik ve Denetim
- `get_domain_info` - Domain güvenlik ayarları
- `get_privileged_groups` - Ayrıcalıklı grup analizi
- `get_user_permissions` - Kullanıcı yetki analizi
- `get_inactive_users` - Aktif olmayan kullanıcılar
- `get_password_policy_violations` - Şifre politikası ihlalleri
- `audit_admin_accounts` - Yönetici hesap denetimi

### 🔧 Sistem Tool'ları
- `test_connection` - LDAP bağlantı testi
- `health` - Sunucu sağlık kontrolü
- `get_schema_info` - Tüm tool'ların şema bilgisi

## 🧪 Test Etme

### HTTP API ile Test

```bash
# Sağlık kontrolü
curl -X POST "http://localhost:8813/activedirectory-mcp" \
  -H "Content-Type: application/json" \
  -d '{"method": "health", "params": {}}'

# Kullanıcıları listele
curl -X POST "http://localhost:8813/activedirectory-mcp" \
  -H "Content-Type: application/json" \
  -d '{"method": "list_users", "params": {"ou": "OU=Users,DC=example,DC=com"}}'

# Yeni kullanıcı oluştur
curl -X POST "http://localhost:8813/activedirectory-mcp" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "create_user", 
    "params": {
      "username": "testuser",
      "password": "TempPass123!",
      "first_name": "Test",
      "last_name": "User",
      "email": "testuser@example.com"
    }
  }'
```

### MCP Inspector ile Test

MCP Inspector kullanarak tool'ları test edebilirsiniz:

```bash
# MCP Inspector'ı yükleyin
npx @modelcontextprotocol/inspector

# HTTP transport ile bağlanın
# URL: http://localhost:8813/activedirectory-mcp
```

## 🐳 Docker ile Production Deployment

### Docker Compose (Önerilen)

```yaml
services:
  activedirectory-mcp:
    build: .
    container_name: ActiveDirectoryMCP
    ports:
      - "8813:8813"
    volumes:
      - ./ad-config:/app/ad-config:ro
    environment:
      - AD_MCP_CONFIG=/app/ad-config/config.json
      - HTTP_HOST=0.0.0.0
      - HTTP_PORT=8813
      - HTTP_PATH=/activedirectory-mcp
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-s", "-f", "http://localhost:8813/activedirectory-mcp"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name activedirectory-mcp.yourdomain.com;
    
    location / {
        proxy_pass http://localhost:8813;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 🔒 Güvenlik Ayarları

### SSL/TLS Konfigürasyonu

```json
{
    "active_directory": {
        "server": "ldaps://dc.example.com:636",
        "use_ssl": true
    },
    "security": {
        "enable_tls": true,
        "validate_certificate": true,
        "ca_cert_file": "/path/to/ca-certificate.pem"
    }
}
```

### Servis Hesabı İzinleri

Minimum gerekli izinler:
- Domain'e okuma erişimi
- Kullanıcı/Grup/Bilgisayar yönetim izinleri
- Şifre sıfırlama izni (gerekirse)
- OU oluşturma/silme izni (gerekirse)

## 📊 Performans Optimizasyonu

```json
{
    "performance": {
        "connection_pool_size": 10,
        "max_retries": 3,
        "retry_delay": 1.0,
        "page_size": 1000
    }
}
```

## 🔍 Sorun Giderme

### Log'ları İnceleme

```bash
# Docker container log'ları
docker logs activedirectory-mcp -f

# Lokal log dosyası
tail -f active_directory_mcp.log
```

### Yaygın Sorunlar

1. **LDAP Bağlantı Hatası**
   ```bash
   # Bağlantıyı test edin
   ldapsearch -H ldap://dc.example.com -D "CN=user,DC=example,DC=com" -W
   ```

2. **Port Kullanımda**
   ```bash
   # Port kontrolü
   netstat -tlnp | grep 8813
   # Farklı port kullanın
   HTTP_PORT=8814 ./start_http_server.sh
   ```

3. **İzin Hatası**
   - Servis hesabı izinlerini kontrol edin
   - OU erişim haklarını doğrulayın

## 📚 Ek Kaynaklar

- [MCP Specification](https://github.com/modelcontextprotocol/specification)
- [FastMCP Documentation](https://github.com/modelcontextprotocol/fastmcp)
- [LDAP3 Library](https://ldap3.readthedocs.io/)
- [Active Directory Schema](https://docs.microsoft.com/en-us/windows/win32/adschema/active-directory-schema)

## 🤝 Destek

Sorunlarınız için:
1. GitHub Issues açın
2. Log dosyalarını paylaşın
3. Konfigürasyon detaylarını (şifreler hariç) ekleyin

---

**🎉 ActiveDirectoryMCP HTTP Transport ile AD yönetiminiz artık hazır!**
