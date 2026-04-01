# 古汉语考据数据库 — 启动与部署指南

## 本地运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动 Web 服务

```bash
python app.py
```

浏览器打开 [http://localhost:5000](http://localhost:5000) 即可访问。

---

## 公网访问（Cloudflare Tunnel — 完全免费，无需注册账号）

Cloudflare Tunnel 可以把你的本地服务映射为一个公网域名，任何电脑/手机都可以通过该域名访问。

### 3. 安装 cloudflared

**Windows（PowerShell）：**
```powershell
irm https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.msi -OutFile cloudflared.msi
.\cloudflared.msi /quiet
```

**macOS：**
```bash
brew install cloudflare/cloudflare/cloudflared
```

**Linux：**
```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
```

### 4. 启动隧道（生成免费域名）

```bash
cloudflared tunnel --url http://localhost:5000
```

执行后会显示类似这样的输出：

```
your-tunnel-name.trycloudflare.com
```

这就是你的公网域名！复制该地址，在**任何设备**的浏览器中打开即可访问。

> 注意：关闭终端窗口后隧道会断开，需要重新运行命令。

### 5. （可选）固定域名

如果希望长期稳定使用，可以注册一个免费 Cloudflare 账号，将隧道绑定到自己的域名。具体操作参见 [Cloudflare Tunnel 官方文档](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)。

---

## 页面功能说明

| 页面 | 地址 | 功能 |
|------|------|------|
| 首页 | `/` | 搜索框 + 数据库统计 |
| 搜索 | `/search?q=字` | 搜索词条和文本片段 |
| 词条列表 | `/terms` | 浏览所有词条 |
| 词条详情 | `/term/<id>` | 查看词条及关联案例 |
| 案例列表 | `/cases` | 浏览所有考据案例 |
| 案例详情 | `/case/<id>` | 查看案例内容与证据 |
| 统计 | `/stats` | 查看数据统计 |
