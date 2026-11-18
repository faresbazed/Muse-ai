# Muse AI — لوحة إدارة التسجيل

أداة Python وواجهة ويب لإدارة تدفقات التسجيل والحسابات والرموز الترويجية الخاصة بـ **`muse.ai`**. تتضمن لوحة Vue 3 وElement Plus، وجدولة الوكلاء الوسيطة (proxies)، ومصادر متعددة للبريد، وإدارة رموز الدعوة. تدعم الواجهة العربية واتجاه RTL.

> **مهم:** التطبيق لا يوفّر تسجيل دخول أو صلاحيات مستخدمين مدمجة. كما أن قاعدة SQLite تحفظ رموز الحسابات وبيانات اعتماد الوكلاء الوسيطة، إلى جانب بيانات أخرى، من دون تشفير. لا تضع اللوحة مباشرة على الإنترنت؛ اتبع إرشادات الوصول الآمن أدناه.

## الوظائف الرئيسية

- تنفيذ تدفق HTTP للمصادقة والتسجيل وتفعيل الجلسة، مع استقبال رموز OTP من موفري البريد المدعومين.
- إدارة الحسابات المستوردة، ومخزون رموز الدعوة، ونتائج التشغيل، والتصدير.
- تشغيل تسجيل فردي أو جدولة دفعات، مع تدوير الوكلاء الوسيطة وحدود للتوقف عند حالات الرفض أو الانتظار.
- اختبار وإدارة مجموعة الوكلاء الوسيطة، وتخزين إعداداتها في SQLite.
- فحص الحسابات المسجلة واسترداد رموز الدعوة وإدارتها.
- واجهة عربية مع تخطيط RTL.

> استخدم المشروع وفق شروط الخدمة والقوانين السارية. لا تتجاوز ضوابط الخدمة أو تستخدمه بما يضر بالآخرين.

## التثبيت على VPS جديد (Ubuntu)

الخطوات التالية مناسبة لخادم Ubuntu 22.04 أو 24.04، مع حساب SSH يملك صلاحية `sudo`. يوصى بـ Python 3.10 أو أحدث. لا تحتاج إلى نطاق إن كنت ستستخدم نفق SSH؛ تحتاج إلى نطاق موجّه إلى عنوان الخادم إذا أردت إعداد الوصول العام عبر HTTPS.

### 1. تحديث الخادم وضبط جدار الحماية

اتصل بالخادم عبر SSH ثم نفّذ:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip ca-certificates ufw
```

اسمح باتصالات SSH قبل تفعيل الجدار الناري:

```bash
sudo ufw allow OpenSSH
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw enable
sudo ufw status
```

إذا كان SSH يستخدم منفذاً غير الافتراضي، اسمح بذلك المنفذ قبل تفعيل UFW. راجع أيضاً قواعد جدار الحماية لدى مزود الـVPS. لا تفتح المنفذ `8766` للعامة.

### 2. إنشاء مستخدم خدمة وتنزيل المشروع

شغّل التطبيق كمستخدم نظام مستقل بدلاً من تشغيله بصلاحيات `root`:

```bash
sudo adduser --system --group --home /opt/muse-ai --no-create-home muse
sudo install -d -o muse -g muse -m 750 /opt/muse-ai
sudo -u muse git clone https://github.com/faresbazed/Muse-ai.git /opt/muse-ai
```

### 3. إنشاء بيئة Python وتثبيت الاعتماديات

```bash
sudo -u muse python3 -m venv /opt/muse-ai/.venv
sudo -u muse /opt/muse-ai/.venv/bin/python -m pip install --upgrade pip
sudo -u muse /opt/muse-ai/.venv/bin/python -m pip install -r /opt/muse-ai/requirements.txt
```

تُقدَّم ملفات الواجهة المبنية داخل المستودع؛ لا يلزم تثبيت Node.js لتشغيل التطبيق.

### 4. إعداد خدمة systemd للتشغيل التلقائي

أنشئ ملف الخدمة:

```bash
sudo tee /etc/systemd/system/muse-ai.service >/dev/null <<'UNIT'
[Unit]
Description=Muse AI Web UI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=muse
Group=muse
WorkingDirectory=/opt/muse-ai
Environment=PYTHONUNBUFFERED=1
UMask=0077
ExecStart=/opt/muse-ai/.venv/bin/python /opt/muse-ai/start_webui.py --host 127.0.0.1 --port 8766 --no-browser
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
UNIT
```

فعّل الخدمة وشغّلها:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now muse-ai
sudo systemctl status muse-ai --no-pager
```

تحقق من سجل الخدمة وصحتها:

```bash
sudo journalctl -u muse-ai -n 100 --no-pager
curl http://127.0.0.1:8766/api/health
```

عند أول تشغيل تُنشأ قاعدة البيانات تلقائياً في `webui/webui.db`.

### 5. الوصول الآمن الموصى به: نفق SSH

الخادم يستمع افتراضياً على `127.0.0.1:8766`، لذلك لا يمكن الوصول إليه مباشرة من الإنترنت. من جهازك، افتح نفقاً:

```bash
ssh -L 8766:127.0.0.1:8766 <مستخدم-SSH>@<عنوان-IP-الخادم>
```

اترك جلسة SSH مفتوحة، ثم افتح `http://127.0.0.1:8766` في متصفح جهازك. لا حاجة إلى فتح منفذ لوحة التحكم في UFW أو في جدار مزود الـVPS.

### الوصول عبر نطاق عام (اختياري)

لا تستخدم هذا الخيار إلا عند الحاجة إلى الوصول من خارج SSH. يتطلب نطاقاً يشير إلى عنوان الخادم، ويفرض HTTPS ومصادقة Basic Auth في Nginx. تظل الخدمة نفسها محصورة على `127.0.0.1`؛ لا تغيّرها إلى `0.0.0.0`.

ثبّت Nginx وCertbot وأداة إنشاء ملف كلمات المرور، ثم اسمح بحركة الويب في الجدار الناري:

```bash
sudo apt install -y nginx apache2-utils certbot python3-certbot-nginx
sudo ufw allow 'Nginx Full'
```

أنشئ مستخدم مصادقة. سيطلب `htpasswd` كلمة المرور تفاعلياً:

```bash
sudo htpasswd -c /etc/nginx/.htpasswd-muse <اسم-مستخدم-للوحة>
sudo chown root:www-data /etc/nginx/.htpasswd-muse
sudo chmod 640 /etc/nginx/.htpasswd-muse
```

أنشئ إعداد HTTP مؤقتاً يستقبل طلب التحقق من الشهادة ثم يوجّه إلى HTTPS. استبدل `panel.example.com` باسم نطاقك:

```bash
sudo tee /etc/nginx/sites-available/muse-ai >/dev/null <<'NGINX'
server {
    listen 80;
    server_name panel.example.com;
    location / {
        return 301 https://$host$request_uri;
    }
}
NGINX
sudo ln -s /etc/nginx/sites-available/muse-ai /etc/nginx/sites-enabled/muse-ai
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx --redirect -d panel.example.com
```

بعد نجاح Certbot، افتح `/etc/nginx/sites-available/muse-ai` وأضف كتلة `location /` التالية **داخل كتلة HTTPS التي أنشأها Certbot (التي تستمع على 443)**. اترك كتلة HTTP لإعادة التوجيه إلى HTTPS كما هي، ولا تضف بيانات المصادقة إليها:

```nginx
location / {
    auth_basic "Muse AI";
    auth_basic_user_file /etc/nginx/.htpasswd-muse;

    proxy_pass http://127.0.0.1:8766;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_read_timeout 3600s;
}
```

تحقق من الإعداد وأعد تحميل Nginx:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

افتح `https://panel.example.com`. تأكد من أن `8766` غير مسموح به في جدار الخادم أو مزود الـVPS. تحمي مصادقة Nginx اللوحة وواجهات API عبر الوكيل العكسي، لكنها ليست تسجيل دخول مدمجاً في التطبيق؛ لا تشغّل الخدمة مكشوفة مباشرة على الإنترنت.

## البيانات والنسخ الاحتياطي

توجد قاعدة البيانات في `webui/webui.db`. قد تحتوي على رموز وصول وجلسات، كلمات مرور أو رموز تحديث للبريد، إعدادات، رموز دعوة، وبيانات اعتماد الوكلاء الوسيطة. لا يشفّر التطبيق ملف SQLite أو نسخه الاحتياطية. يحدّ `UMask=0077` في خدمة systemd من صلاحيات الملفات الجديدة؛ حافظ على ملكية مجلد المشروع لمستخدم `muse`، ولا تشارك قاعدة البيانات أو تضعها في Git أو في تخزين نسخ احتياطية عام.

لإنشاء نسخة متسقة، أوقف الخدمة مؤقتاً ثم انسخ قاعدة البيانات إلى مجلد خاص:

```bash
sudo systemctl stop muse-ai
sudo install -d -m 700 /var/backups/muse-ai
sudo cp /opt/muse-ai/webui/webui.db "/var/backups/muse-ai/webui-$(date +%F-%H%M%S).db"
sudo chown root:root /var/backups/muse-ai/*.db
sudo chmod 600 /var/backups/muse-ai/*.db
sudo systemctl start muse-ai
```

احمِ النسخ الاحتياطية مثل قاعدة البيانات الأصلية، وشفّرها إذا نُقلت إلى خارج الخادم. للاستعادة، أوقف الخدمة، انسخ النسخة المطلوبة إلى `/opt/muse-ai/webui/webui.db`، ثم أعد الملكية إلى `muse:muse` والصلاحيات إلى `600` وشغّل الخدمة من جديد.

## تحديث التطبيق ومتابعة الخدمة

بعد تنزيل التغييرات من المستودع:

```bash
sudo systemctl stop muse-ai
sudo -u muse git -C /opt/muse-ai pull --ff-only
sudo -u muse /opt/muse-ai/.venv/bin/python -m pip install -r /opt/muse-ai/requirements.txt
sudo systemctl start muse-ai
```

لعرض السجل مباشرة أو إعادة تشغيل الخدمة:

```bash
sudo journalctl -u muse-ai -f
sudo systemctl restart muse-ai
```

## تشغيل محلي سريع

على جهاز تطوير يدعم Python 3.10 أو أحدث:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python start_webui.py --host 127.0.0.1 --port 8766 --no-browser
```

افتح `http://127.0.0.1:8766`. في Windows يمكن استخدام `启动服务.bat` و`停止服务.bat`.

لإعادة بناء الواجهة بعد تعديل ملفاتها، يلزم Node.js 18 أو أحدث:

```bash
cd webui/frontend
npm ci
npm run build
```

## تكامل iCloud الاختياري

يتوقع `import_icloud.py` افتراضياً قاعدة بيانات خدمة iCloud في `../icloud/data/workbench.db`، ويمكن تغيير مسار قاعدة البيانات عبر `ICLOUD_DB_PATH`. يعمل هذا التكامل فقط إذا كانت قاعدة البيانات وخدمة ترحيل البريد متاحة من خادم التطبيق؛ عناوين الترحيل التي ينشئها السكربت تستخدم `127.0.0.1:4173`، لذا يجب أن تعمل خدمة الترحيل على الخادم نفسه وعلى ذلك المنفذ. تغيير `ICLOUD_DB_PATH` وحده لا يغيّر عنوان خدمة الترحيل. إن لم يكن التكامل المحلي متاحاً، استخدم استيراد البريد من لوحة التحكم.

مثال لمزامنة عشرة عناوين من الخادم:

```bash
sudo -u muse env ICLOUD_DB_PATH=/المسار/إلى/workbench.db \
  /opt/muse-ai/.venv/bin/python /opt/muse-ai/import_icloud.py --limit 10
```

## اختبارات الدخان

```bash
python test_onboarding_smoke.py
python test_runner_smoke.py
python test_webui_smoke.py
```

## إخلاء المسؤولية

هذا المشروع لأغراض التعلم والبحث الشخصي. أنت مسؤول عن الالتزام بشروط خدمات الأطراف الأخرى والقوانين واللوائح ذات الصلة.
