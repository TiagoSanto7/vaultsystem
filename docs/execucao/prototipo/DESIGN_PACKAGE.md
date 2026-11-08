# Design System — Petrovina Internal Apps

> Referência visual para replicar o estilo dos sistemas internos da Petrovina em novos projetos. Inclui design tokens, componente de sidebar completo, layout base e instruções de comportamento.

---

## 1. Identidade Visual

### Direção Estética

**Industrial/utilitário com toque corporativo verde.**
- Tom sério, funcional, sem ornamento desnecessário
- Fundo escuro por padrão (dark-first)
- Cor primária: **verde Petrovina `#007800`**
- Tipografia limpa e técnica: **Ubuntu** (não usar Inter, Roboto ou Arial)
- Espaçamento generoso, hierarquia clara

---

## 2. Dependências Externas (CDN)

Cole no `<head>` de qualquer novo projeto:

```html
<!-- Fonte Ubuntu -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Ubuntu:wght@300;400;500;700&display=swap" rel="stylesheet">

<!-- Bootstrap 5.3.0 -->
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">

<!-- Font Awesome 6.4.0 -->
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">

<!-- Bootstrap Icons 1.11.1 -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">

<!-- SweetAlert2 (tema dark por padrão, troca por JS se light) -->
<link id="swal-theme" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@sweetalert2/theme-dark@5/dark.css">
```

Cole antes do `</body>`:

```html
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
```

---

## 3. Design Tokens — CSS Variables

Cole no início do seu arquivo `.css`:

```css
/* ===== BASE ===== */
* {
    font-family: "Ubuntu", sans-serif;
    font-weight: 300;
    font-style: normal;
}

/* ===== TEMA ESCURO (padrão) ===== */
:root,
[data-theme="dark"] {
    /* Backgrounds */
    --bg-body: #343a40;
    --bg-sidebar: #2d3136;
    --bg-hover: rgba(255, 255, 255, 0.1);
    --bg-active: rgba(0, 120, 0, 0.2);
    --bg-danger: rgba(255, 0, 0, 0.1);
    --bg-danger-hover: rgba(255, 0, 0, 0.2);

    /* Cores principais */
    --color-primary: #007800;        /* Verde Petrovina */
    --color-primary-hover: #b24407;  /* Laranja no hover */
    --color-info: #0294ce;
    --color-danger: #ff6b6b;
    --color-success: #198754;

    /* Texto */
    --color-text: #ffffff;
    --color-text-muted: #b0b3b8;
    --color-text-input: #adb5bd;

    /* Bordas e inputs */
    --border-color: #454d55;
    --border-input: #495057;
    --input-bg: #2b3035;

    /* Tabelas */
    --table-border: #2f3d34;
    --table-header-bg: #1c3a23;
    --table-header-text: #e9f2ea;
    --table-row-bg: #2f3531;
    --table-row-alt: #262f2b;
    --table-row-hover: #334338;
    --table-text: #e6efe8;

    /* Cards e modais */
    --card-bg: #343a40;
    --card-header-bg: var(--bg-body);
    --modal-bg: #2d3136;

    /* Admin tables */
    --admin-table-bg: rgba(255, 255, 255, 0.05);
    --admin-table-th-bg: rgba(255, 255, 255, 0.1);
    --admin-table-th-text: rgba(255, 255, 255, 0.7);
    --admin-table-td-border: rgba(255, 255, 255, 0.05);

    /* Módulos da home */
    --home-module-bg: #0e3515;
    --home-module-text: rgba(240, 248, 255, 0.816);
    --home-card-border: rgba(255, 255, 255, 0.37);
    --home-card-text-muted: rgba(255, 255, 255, 0.5);

    /* Paginação */
    --pagination-disabled-bg: #212529;
    --pagination-disabled-text: #6c757d;

    /* Gradientes */
    --body-gradient-start: #2a3530;
    --body-gradient-end: #1e2329;
    --sidebar-gradient-end: #252930;

    /* Overlay SAP */
    --sap-overlay-bg: rgba(45, 49, 54, 0.95);

    /* Grain */
    --grain-opacity: 0.025;
}

/* ===== TEMA CLARO ===== */
[data-theme="light"] {
    --bg-body: #f0f2f5;
    --bg-sidebar: #ffffff;
    --bg-hover: rgba(0, 0, 0, 0.06);
    --bg-active: rgba(0, 120, 0, 0.1);
    --bg-danger: rgba(255, 0, 0, 0.06);
    --bg-danger-hover: rgba(255, 0, 0, 0.12);

    --color-primary: #007800;
    --color-primary-hover: #c25510;
    --color-info: #0277a8;
    --color-danger: #dc3545;
    --color-success: #198754;
    --color-text: #1a1a1a;
    --color-text-muted: #6c757d;
    --color-text-input: #6c757d;

    --border-color: #dee2e6;
    --border-input: #ced4da;
    --input-bg: #ffffff;

    --table-border: #dee2e6;
    --table-header-bg: #e8f5e9;
    --table-header-text: #1a3a1a;
    --table-row-bg: #ffffff;
    --table-row-alt: #f8faf8;
    --table-row-hover: #e8f0ea;
    --table-text: #2d2d2d;

    --card-bg: #ffffff;
    --card-header-bg: #f8f9fa;
    --modal-bg: #ffffff;
    --admin-table-bg: #ffffff;
    --admin-table-th-bg: #f1f3f5;
    --admin-table-th-text: #495057;
    --admin-table-td-border: #e9ecef;

    --home-module-bg: #e8f5e9;
    --home-module-text: #2d5a2d;
    --home-card-border: #dee2e6;
    --home-card-text-muted: #6c757d;

    --pagination-disabled-bg: #e9ecef;
    --pagination-disabled-text: #adb5bd;

    --body-gradient-start: #e8ede9;
    --body-gradient-end: #dfe3e8;
    --sidebar-gradient-end: #f8f9fa;

    --sap-overlay-bg: rgba(255, 255, 255, 0.95);

    --grain-opacity: 0.015;
}
```

---

## 4. Body e Background

```css
body {
    background: radial-gradient(
        ellipse at 15% 40%,
        var(--body-gradient-start) 0%,
        var(--bg-body) 45%,
        var(--body-gradient-end) 100%
    );
    background-attachment: fixed;
    margin: 0;
    padding: 0;
    min-height: 100vh;
    color: var(--color-text);
    transition: background 0.3s ease, color 0.3s ease;
}

/* Grain texture — profundidade sutil sem peso visual */
body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
    opacity: var(--grain-opacity);
    pointer-events: none;
    z-index: 0;
}
```

---

## 5. Componente Sidebar (Navbar)

### 5.1 HTML

> Para projetos **não-Flask**, remova os blocos `{% if %}` e `{{ url_for(...) }}` e substitua pelos caminhos diretos.

```html
<!-- Sidebar Navbar -->
<div class="sidebar closed" id="sidebar">

    <!-- Logo -->
    <div class="sidebar-logo">
        <img src="/static/favicon.png" alt="Logo" class="logo-img">
        <span class="logo-text">Nome do Sistema</span>
    </div>

    <!-- Navegação -->
    <nav class="sidebar-nav">
        <ul class="nav-list">

            <!-- Item simples -->
            <li class="nav-item">
                <a href="/" class="nav-link active">
                    <i class="fas fa-home"></i>
                    <span class="nav-text">Página Inicial</span>
                </a>
            </li>

            <!-- Separador de seção -->
            <li class="nav-item mt-3">
                <span class="nav-text text-white-50 ms-3"
                      style="font-size: 0.7rem; text-transform: uppercase;">
                    Seção
                </span>
            </li>

            <!-- Mais itens -->
            <li class="nav-item">
                <a href="/pagina-1" class="nav-link">
                    <i class="bi bi-box-seam-fill"></i>
                    <span class="nav-text">Página 1</span>
                </a>
            </li>
            <li class="nav-item">
                <a href="/pagina-2" class="nav-link">
                    <i class="fas fa-boxes"></i>
                    <span class="nav-text">Página 2</span>
                </a>
            </li>

        </ul>
    </nav>

    <!-- Footer: Tema + Logout -->
    <div class="sidebar-footer">
        <button class="theme-toggle-btn" id="theme-toggle" type="button"
                title="Alternar tema claro/escuro">
            <i class="fas fa-sun" id="theme-icon"></i>
            <span class="nav-text" id="theme-label">Tema Claro</span>
        </button>
        <a href="/logout" class="btn-logout mt-2">
            <i class="fas fa-sign-out-alt"></i>
            <span class="nav-text">Sair</span>
        </a>
    </div>
</div>

<!-- Botão Hamburger -->
<button class="hamburger" id="hamburger-btn">
    <span></span>
    <span></span>
    <span></span>
</button>
```

### 5.2 CSS da Sidebar

```css
/* ===== SIDEBAR ===== */
.sidebar {
    position: fixed;
    top: 0;
    left: 0;
    width: 250px;
    height: 100vh;
    background: linear-gradient(180deg, var(--bg-sidebar) 0%, var(--sidebar-gradient-end) 100%);
    color: var(--color-text);
    display: flex;
    flex-direction: column;
    box-shadow: 2px 0 12px rgba(0, 0, 0, 0.4);
    transition: transform 0.3s ease;
    z-index: 999;
}

.sidebar.closed {
    width: 72px;
}

/* Logo */
.sidebar-logo {
    padding: 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    border-bottom: 1px solid var(--border-color);
    position: relative;
    z-index: 1000;
}

.sidebar.closed .sidebar-logo {
    justify-content: center;
    padding: 20px 10px;
}

.logo-img {
    width: 40px;
    height: 40px;
    border-radius: 8px;
    flex-shrink: 0;
}

.logo-text {
    font-size: 18px;
    font-weight: 500;
    color: var(--color-text);
    white-space: nowrap;
}

.sidebar.closed .logo-text {
    display: none;
}

/* Nav */
.sidebar-nav {
    flex: 1;
    padding: 20px 0;
    overflow-y: auto;
}

.nav-list {
    list-style: none;
    padding: 0;
    margin: 0;
}

.nav-item {
    margin: 0;
}

.nav-link {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 20px;
    color: var(--color-text-muted);
    text-decoration: none;
    transition: all 0.3s ease;
    border-left: 3px solid transparent;
}

.sidebar.closed .nav-link {
    justify-content: center;
    padding: 12px 0;
}

.sidebar.closed .nav-text {
    display: none;
}

.nav-link:hover {
    background-color: var(--bg-hover);
    color: var(--color-text);
    border-left-color: var(--color-primary);
}

.nav-link.active {
    background-color: var(--bg-active);
    color: var(--color-text);
    border-left-color: var(--color-primary);
}

.nav-link i {
    width: 20px;
    text-align: center;
    flex-shrink: 0;
}

.nav-text {
    white-space: nowrap;
}

/* Footer */
.sidebar-footer {
    padding: 20px;
    border-top: 1px solid var(--border-color);
}

.sidebar.closed .sidebar-footer {
    padding: 20px 10px;
}

/* Botão de tema */
.theme-toggle-btn {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 20px;
    background: transparent;
    border: none;
    color: var(--color-text-muted);
    cursor: pointer;
    width: 100%;
    transition: all 0.3s ease;
    border-left: 3px solid transparent;
}

.sidebar.closed .theme-toggle-btn {
    justify-content: center;
    padding: 12px 0;
}

.sidebar.closed .theme-toggle-btn .nav-text {
    display: none;
}

.theme-toggle-btn:hover {
    background-color: var(--bg-hover);
    color: var(--color-text);
    border-left-color: var(--color-primary);
}

/* Botão de logout */
.btn-logout {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    background-color: var(--bg-danger);
    color: var(--color-danger);
    text-decoration: none;
    border-radius: 6px;
    transition: all 0.3s ease;
    border: 1px solid transparent;
}

.sidebar.closed .btn-logout {
    justify-content: center;
    padding: 12px 0;
}

.sidebar.closed .btn-logout .nav-text {
    display: none;
}

.btn-logout:hover {
    background-color: var(--bg-danger-hover);
    color: var(--color-text);
    border-color: var(--color-danger);
}

.btn-logout i {
    width: 20px;
    text-align: center;
}

/* Hamburger */
.hamburger {
    position: fixed;
    top: 15px;
    left: 15px;
    width: 40px;
    height: 40px;
    background-color: transparent;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 5px;
    z-index: 1001;
    transition: left 0.3s ease;
}

.hamburger span {
    width: 24px;
    height: 3px;
    background-color: var(--color-text);
    border-radius: 2px;
    display: block;
}

/* Hamburger se move junto com a sidebar */
.sidebar:not(.closed) ~ .hamburger {
    left: 265px;
}
.sidebar.closed ~ .hamburger {
    left: 84px;
}

/* Main Content */
.main-content {
    margin-left: 250px;
    transition: margin-left 0.3s ease;
    padding-top: 60px;
    position: relative;
    min-height: 100vh;
}

.main-content.closed {
    margin-left: 72px;
}

/* ===== RESPONSIVO ===== */
@media (max-width: 768px) {
    .sidebar { width: 250px; }
    .main-content { margin-left: 0; }
    .sidebar.closed { transform: translateX(-100%); width: 250px; }
    .main-content.closed { margin-left: 0; }
    .logo-text { display: none; }
}
```

---

## 6. JavaScript — Tema e Sidebar

Cole no seu `main.js` (ou em `<script>` no HTML):

```javascript
// ===== TEMA: aplicar ANTES do DOMContentLoaded para evitar flash =====
// Coloque este bloco inline no <head>, ANTES de qualquer CSS carregado
(function() {
    const saved = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);

    // Troca tema do SweetAlert2 se tiver o link com id="swal-theme"
    const swalLink = document.getElementById('swal-theme');
    if (saved === 'light' && swalLink) {
        swalLink.href = 'https://cdn.jsdelivr.net/npm/@sweetalert2/theme-default@5/default.css';
    }
})();

// ===== SIDEBAR: Toggle abrir/fechar =====
document.addEventListener('DOMContentLoaded', () => {
    const sidebar      = document.getElementById('sidebar');
    const mainContent  = document.getElementById('main-content');
    const hamburgerBtn = document.getElementById('hamburger-btn');

    hamburgerBtn?.addEventListener('click', () => {
        sidebar.classList.toggle('closed');
        mainContent?.classList.toggle('closed');
    });

    // ===== TEMA: Toggle claro/escuro =====
    const themeToggle = document.getElementById('theme-toggle');
    const themeIcon   = document.getElementById('theme-icon');
    const themeLabel  = document.getElementById('theme-label');
    const swalTheme   = document.getElementById('swal-theme');

    function updateThemeUI(theme) {
        if (!themeIcon || !themeLabel) return;
        if (theme === 'dark') {
            themeIcon.className = 'fas fa-sun';
            themeLabel.textContent = 'Tema Claro';
            if (swalTheme) swalTheme.href = 'https://cdn.jsdelivr.net/npm/@sweetalert2/theme-dark@5/dark.css';
        } else {
            themeIcon.className = 'fas fa-moon';
            themeLabel.textContent = 'Tema Escuro';
            if (swalTheme) swalTheme.href = 'https://cdn.jsdelivr.net/npm/@sweetalert2/theme-default@5/default.css';
        }
    }

    // Sincronizar UI com o tema salvo ao carregar
    updateThemeUI(localStorage.getItem('theme') || 'dark');

    themeToggle?.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme') || 'dark';
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('theme', next);
        updateThemeUI(next);
    });

    // ===== ACTIVE LINK: marcar link ativo automaticamente =====
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
        const href = link.getAttribute('href');
        if (href && href !== '#' && currentPath.startsWith(href)) {
            link.classList.add('active');
        }
    });
});
```

---

## 7. Layout Base — HTML Completo

Esqueleto mínimo para um novo projeto:

```html
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Petrovina — Nome do Sistema</title>

    <!-- Tema aplicado antes do CSS para evitar flash -->
    <script>
        (function(){
            var t = localStorage.getItem('theme') || 'dark';
            document.documentElement.setAttribute('data-theme', t);
            var s = document.getElementById('swal-theme');
            if (t === 'light' && s) s.href = 'https://cdn.jsdelivr.net/npm/@sweetalert2/theme-default@5/default.css';
        })();
    </script>

    <!-- Fontes -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Ubuntu:wght@300;400;500;700&display=swap" rel="stylesheet">

    <!-- Libs -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
    <link id="swal-theme" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@sweetalert2/theme-dark@5/dark.css">

    <!-- CSS do projeto -->
    <link href="/static/styles.css" rel="stylesheet">
</head>
<body>

    <!-- Sidebar (copiar de seção 5.1) -->

    <!-- Conteúdo principal -->
    <main class="main-content closed" id="main-content">
        <div class="container-fluid mt-5">

            <!-- Seu conteúdo aqui -->

        </div>
    </main>

    <!-- Scripts -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
    <script src="/static/js/main.js"></script>
</body>
</html>
```

---

## 8. Componentes Reutilizáveis

### Tabela padrão

```html
<div class="table-wrapper">
    <table class="table table-striped table-producoes">
        <thead class="table-secondary">
            <tr>
                <th>Coluna 1</th>
                <th>Coluna 2</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Valor</td>
                <td>Valor</td>
                <td><span class="badge bg-warning text-dark">Pendente</span></td>
            </tr>
        </tbody>
    </table>
</div>
```

CSS necessário (além das variáveis):

```css
.table-wrapper {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid var(--table-border);
    background-color: var(--bg-sidebar);
}

.table-producoes {
    margin-bottom: 0;
    color: var(--table-text);
}

.table-producoes thead.table-secondary {
    background-color: var(--table-header-bg);
    color: var(--table-header-text);
}

.table-producoes thead th {
    border-bottom: 1px solid var(--table-border);
    font-weight: 500;
}

.table-producoes td,
.table-producoes th {
    border-color: var(--table-border);
    vertical-align: middle;
}

.table-producoes tbody tr {
    background-color: var(--table-row-bg);
}

.table-producoes.table-striped > tbody > tr:nth-of-type(odd) {
    background-color: var(--table-row-alt);
}

.table-producoes tbody tr:hover {
    background-color: var(--table-row-hover);
}
```

### Botões padrão

```html
<!-- Ação primária (verde) -->
<button class="btn btn-sincronizar">
    <i class="fas fa-sync-alt me-1"></i> Sincronizar
</button>

<!-- Ação de integração (azul) -->
<button class="btn btn-sincronizar-sap">
    <i class="fas fa-plug me-1"></i> Integrar SAP
</button>
```

```css
.btn-sincronizar {
    background-color: var(--color-primary);
    color: var(--color-text);
    border: none;
    transition: 0.3s;
}

.btn-sincronizar:hover {
    background-color: var(--color-primary-hover);
    color: var(--color-text);
}

.btn-sincronizar-sap {
    background-color: var(--color-info);
    color: var(--color-text);
    border: none;
    transition: 0.3s;
}
```

### Paginação

```css
.pagination .page-link {
    background-color: var(--bg-sidebar);
    border-color: var(--table-border);
    color: var(--table-text);
    border-radius: 8px;
    padding: 6px 12px;
    transition: 0.2s ease;
}

.pagination .page-item.active .page-link {
    background-color: var(--table-row-hover);
    border-color: var(--border-color);
    color: var(--color-text);
    font-weight: 500;
}

.pagination .page-item.disabled .page-link {
    background-color: var(--pagination-disabled-bg);
    color: var(--pagination-disabled-text);
    opacity: 0.7;
}

.pagination .page-link:hover {
    background-color: var(--table-row-hover);
    color: var(--color-text);
}

.pagination {
    gap: 6px;
}
```

### Info card (para dashboards)

```html
<div class="col-md-3 col-6">
    <div class="p-2 border border-secondary rounded"
         style="background: rgba(255,255,255,0.03)">
        <div style="font-size:0.68rem; color:#9ca3af; text-transform:uppercase;
                    letter-spacing:0.06em; margin-bottom:2px">
            Label
        </div>
        <div class="fw-semibold" style="font-size:0.88rem">Valor</div>
    </div>
</div>
```

---

## 9. Checklist de Implementação

Ao iniciar um novo projeto com este design system:

- [ ] Importar as fontes e libs da seção 2
- [ ] Copiar o bloco de CSS variables completo (seção 3)
- [ ] Adicionar body + grain texture (seção 4)
- [ ] Copiar o HTML da sidebar (seção 5.1)
- [ ] Copiar o CSS da sidebar (seção 5.2)
- [ ] Adicionar o JS de tema + sidebar (seção 6)
- [ ] Estruturar o layout com `main.main-content.closed` e `id="main-content"`
- [ ] Aplicar o snippet anti-flash de tema no `<head>` antes dos CSS links
- [ ] Adaptar os links da sidebar para as rotas do novo projeto
- [ ] Trocar `Logo`/`Nome do Sistema` pelo nome correto

---

## 10. Notas de Adaptação

| Situação | O que fazer |
|---|---|
| Projeto **não usa Flask** | Remover `{{ url_for(...) }}` e `{% if %}`, usar paths diretos |
| Projeto **não tem logout** | Remover o `.btn-logout` do footer da sidebar |
| Projeto **não tem toggle de tema** | Remover `.theme-toggle-btn`, simplificar o footer |
| Adicionar nova seção ao menu | Copiar padrão `<li class="nav-item mt-3"><span class="nav-text...">` |
| Adicionar item ao menu | Copiar qualquer `<li class="nav-item">` com `nav-link` e ícone FA/BI |
| Cor primária diferente | Alterar `--color-primary` e `--color-primary-hover` nas duas seções |
