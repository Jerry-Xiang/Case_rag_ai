# GitHub 上传指令

## 准备工作

1. 确保已安装 Git：
   ```bash
   git --version
   ```

2. 如果未安装 Git，请先安装：
   - Windows：从 https://git-scm.com/download/win 下载安装
   - macOS：`brew install git`
   - Linux：`sudo apt install git`

## 配置 Git

```bash
# 配置用户名
git config --global user.name "Your Name"

# 配置邮箱
git config --global user.email "your.email@example.com"

# 查看配置
git config --list
```

## 创建 GitHub 仓库

1. 登录 GitHub：https://github.com
2. 点击右上角 "New" 按钮创建新仓库
3. 填写仓库信息：
   - Repository name：`Case_rag_ai`
   - Description：`基于 Qwen-Agent 框架构建的智能问答系统`
   - Public/Private：选择 Public
   - 不要勾选 "Add a README file"（我们已有 README.md）
   - 点击 "Create repository"

## 初始化本地仓库

```bash
# 进入项目目录
cd Case_rag_ai

# 初始化 Git 仓库
git init

# 添加所有文件
git add .

# 查看状态
git status
```

## 创建 .gitignore 文件

创建 `.gitignore` 文件，排除不需要上传的文件：

```bash
# 创建 .gitignore
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv/
*.egg-info/
dist/
build/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Logs
*.log
app_start.log

# Environment
.env
.env.local
.env.*.local

# Workspace
workspace/
*.png
*.pdf

# Config
harness/config.yaml

# Cache
.cache/
node_modules/
EOF
```

## 提交代码

```bash
# 重新添加文件（排除 .gitignore 中的文件）
git add .

# 查看状态
git status

# 提交代码
git commit -m "feat: 初始化 Case RAG AI 项目"
```

## 关联远程仓库

```bash
# 添加远程仓库（替换为你的仓库地址）
git remote add origin https://github.com/your-username/Case_rag_ai.git

# 查看远程仓库
git remote -v
```

## 推送到 GitHub

```bash
# 推送代码到 main 分支
git push -u origin main
```

## 如果需要推送新的修改

```bash
# 添加修改的文件
git add .

# 提交修改
git commit -m "feat: 添加新功能"

# 推送修改
git push
```

## 常见问题

### 推送失败：403 Forbidden

**原因**：GitHub 账号密码验证失败

**解决方案**：使用 Personal Access Token 代替密码

1. 登录 GitHub，进入 Settings → Developer settings → Personal access tokens
2. 生成新的 Token，勾选 `repo` 权限
3. 使用 Token 作为密码进行推送

### 推送失败：remote: Repository not found

**原因**：远程仓库地址错误

**解决方案**：检查远程仓库地址是否正确

```bash
git remote -v
git remote set-url origin https://github.com/your-username/Case_rag_ai.git
```

### 推送失败：fatal: remote origin already exists

**原因**：远程仓库已存在

**解决方案**：删除旧的远程仓库，重新添加

```bash
git remote remove origin
git remote add origin https://github.com/your-username/Case_rag_ai.git
```

### 推送失败：Updates were rejected because the remote contains work that you do not have locally

**原因**：远程仓库有本地没有的修改

**解决方案**：拉取远程修改，合并后再推送

```bash
git pull origin main --allow-unrelated-histories
git push origin main
```

## 分支管理

```bash
# 创建新分支
git checkout -b feature/new-feature

# 切换分支
git checkout main

# 合并分支
git checkout main
git merge feature/new-feature

# 删除分支
git branch -d feature/new-feature
```

## 标签管理

```bash
# 创建标签
git tag -a v1.0.0 -m "版本 1.0.0"

# 推送标签
git push origin v1.0.0

# 查看标签
git tag -l
```

---

*文档生成时间：2026-07-06*
