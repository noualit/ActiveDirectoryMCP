# ActiveDirectoryMCP Testing Guide

Bu kılavuz, ActiveDirectoryMCP'yi farklı test senaryolarında nasıl test edeceğinizi açıklar.

## 🧪 Test Türleri

### 1. **Unit Tests (Mock/Stub) - ✅ Çalışıyor**
Gerçek LDAP sunucusu gerektirmez, mock verilerle çalışır.

```bash
# Tüm testleri çalıştır
pytest -v

# Sadece specific testler
pytest tests/test_config.py -v
pytest tests/test_user_tools.py -v

# Test sonucu: 43/43 geçiyor ✅
```

**Avantajları:**
- Hızlı çalışır
- Network gerektirmez  
- Hata senaryolarını test eder
- CI/CD için ideal

### 2. **Integration Tests (Real LDAP) - Opsiyonel**
Gerçek LDAP/AD sunucusu gerektirir.

## 🔧 Gerçek AD ile Test

### Gereksinimler
- Active Directory sunucusuna erişim
- Service account credentials
- Network bağlantısı

### Adımlar

1. **Config dosyasını hazırla:**
```bash
cp ad-config/config.example.json ad-config/config.json
# config.json'u gerçek AD bilgilerinle düzenle
```

2. **Gerçek bağlantıyı test et:**
```bash
export AD_MCP_CONFIG=ad-config/config.json
python test_real_ad.py
```

3. **Beklenen çıktı:**
```
🔗 Real Active Directory Connection Test
✅ Config loaded: ldap://dc.company.com:389
✅ LDAP Manager initialized  
✅ Connected to: dc.company.com:389
🔍 Testing user listing...
✅ Found 150 users
   1. John Smith (jsmith)
   2. Jane Doe (jdoe)
   3. Mike Wilson (mwilson)
🎉 Real AD test successful!
```

## 🐳 Docker Test LDAP Sunucusu

Gerçek AD yoksa, test LDAP sunucusu kullanın:

### 1. Test LDAP Sunucusunu Başlat
```bash
# Test LDAP sunucusunu çalıştır
docker-compose -f docker-test-ldap.yml up -d

# Sunucunun hazır olmasını bekle (30 saniye)
sleep 30
```

### 2. Test Config'i Kullan
```bash
export AD_MCP_CONFIG=ad-config/test-ldap-config.json
python test_real_ad.py
```

### 3. LDAP Admin Arayüzü
Test verilerini görmek için: http://localhost:8080
- **Login DN**: `cn=admin,dc=test,dc=local`
- **Password**: `admin123`

### 4. Test Verileri
Docker sunucusu şu test verilerini içerir:
- **3 kullanıcı**: jdoe, jsmith, testadmin
- **4 grup**: IT Department, Sales Team, Administrators, All Users
- **OU yapısı**: people, groups, computers, service_accounts

## 🔍 Manuel LDAP Test

### LDAP bağlantısını manuel test et:
```bash
# Bağlantı testi
ldapsearch -x -H ldap://localhost:389 \
  -D "cn=admin,dc=test,dc=local" \
  -w admin123 \
  -b "dc=test,dc=local" \
  "(objectClass=*)"

# Kullanıcıları listele
ldapsearch -x -H ldap://localhost:389 \
  -D "cn=admin,dc=test,dc=local" \
  -w admin123 \
  -b "ou=people,dc=test,dc=local" \
  "(objectClass=inetOrgPerson)"
```

## 📊 Test Senaryoları

### Başarılı Test Göstergeleri

#### ✅ Unit Tests
```
================================ 43 passed, 2 warnings in 3.03s ======================================
```

#### ✅ Real AD Test
```
✅ Connected to: dc.company.com:389
✅ Found 150 users
🎉 Real AD test successful!
```

#### ✅ Docker LDAP Test
```
✅ Connected to: localhost:389  
✅ Found 3 users
   1. John Doe (jdoe)
   2. Jane Smith (jsmith)
   3. Test Admin (testadmin)
```

### Hata Senaryoları

#### ❌ Config Eksik
```
❌ Config file not found!
   Expected: ad-config/config.json
```
**Çözüm**: Config dosyasını oluştur ve düzenle

#### ❌ Bağlantı Hatası
```
❌ Connection failed: [Errno 111] Connection refused
```
**Çözüm**: 
- Sunucu çalışıyor mu kontrol et
- Firewall ayarlarını kontrol et
- Port numarasını doğrula

#### ❌ Kimlik Doğrulama Hatası
```
❌ Authentication failed: Invalid credentials
```
**Çözüm**:
- Username/password kontrolü
- Bind DN formatını kontrol et
- Account kilidi var mı kontrol et

## 🚀 HTTP Server Test

### HTTP transport'u test et:
```bash
# HTTP sunucusunu başlat
./start_http_server.sh

# Başka terminal'de test et
python test_scripts/test_http_server.py

# Beklenen çıktı:
# ✅ Server is available!
# ✅ Health Check
# ✅ Success
```

## 🔄 CI/CD Pipeline

### GitHub Actions Örneği
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Setup Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.11'
    - name: Install dependencies
      run: |
        pip install -e ".[dev]"
    - name: Run unit tests
      run: |
        pytest -v
    - name: Test Docker LDAP
      run: |
        docker-compose -f docker-test-ldap.yml up -d
        sleep 30
        export AD_MCP_CONFIG=ad-config/test-ldap-config.json
        python test_real_ad.py
```

## 📝 Test Checklist

- [ ] **Unit Tests**: 43/43 geçiyor
- [ ] **Config validation**: Geçersiz config test edildi
- [ ] **Mock scenarios**: Error handling test edildi
- [ ] **Real AD connection**: Gerçek sunucuyla test edildi
- [ ] **HTTP transport**: HTTP endpoint'ler test edildi
- [ ] **Docker LDAP**: Test sunucusuyla test edildi

## 💡 İpuçları

1. **Development**: Unit tests yeterli
2. **Production deployment**: Real AD test şart
3. **CI/CD**: Docker LDAP kullan
4. **Debugging**: LDAP admin arayüzü kullan
5. **Performance**: Test verilerini küçük tut

---

**🎯 Test stratejisi: Unit tests ile hızlı development, integration tests ile production confidence!**
