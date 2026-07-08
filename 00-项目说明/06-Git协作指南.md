# Git 协作指南

如果你的任务是人工标注，先按本文完成 clone、分支和 PR 的基本操作，再看 `07-标注工作台使用流程.md`。标注工作台会在本地网页中生成 JSON 文件，最后仍然通过自己的分支提交。

## 1. Git 下载与设置

Windows：打开 https://git-scm.com/download/win 下载 Git for Windows，安装时大部分选项保持默认。安装后打开 `Git Bash`。

macOS：打开 Terminal，执行：

```bash
xcode-select --install
```

检查 Git 是否安装成功：

```bash
git --version
```

第一次使用 Git，需要设置提交记录里的姓名和邮箱：

```bash
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"
```

检查设置：

```bash
git config --global --list
```



## 2. Clone 与打开项目

选择一个本地目录，例如 Windows 的 `D:\projects` 或 macOS 的 `~/Projects`，然后执行：

```bash
git clone https://github.com/seraphic663/gaoyou-erwang-knowledge-base.git
cd gaoyou-erwang-knowledge-base
```

用 VS Code 打开项目：

```bash
code .
```

如果 `code .` 不可用，可以直接在 VS Code 里选择 `File -> Open Folder`，打开刚 clone 下来的项目文件夹。

第一次 push 时，Git 可能要求登录 GitHub。按终端提示走浏览器登录即可；如果提示密码不支持，需要用 GitHub token 或重新按提示网页登录。遇到认证问题，把完整报错截图发给负责人。



## ==接下来内容暂时不用看，也暂时不要修改文件==

 

## 3. 基本注意事项

不要直接在 `main` 分支上改。成员在自己的分支上写，写完提交 Pull Request，由负责人审核后合并到 `main`。

不要提交这些内容：

- `.env`、API key、账号密码、token。
- `05-归档文献/` 中的 PDF、DOCX、扫描件、签名图片、大型归档材料。
- `node_modules/`。
- `__pycache__/`、`*.pyc`。
- `.db-wal`、`.db-shm`、`.db-journal`。
- Word 临时文件，例如 `~$xxx.docx`。
- 个人草稿、私人规划、临时笔记。

如果不确定某个文件能不能提交，先运行：

```bash
git status
```

看到 `.env`、大型 PDF、缓存目录、私人草稿时，不要直接 `git add .`，先问负责人。



## 4. 基本指令

```bash
git status							# 查看当前状态：哪些文件被修改等
git branch							# 查看当前分支
git pull							# 拉取远程仓库的最新版本
git switch -c docs-my-task			# 新建并切换到一个任务分支
git switch <branch_name>			# 切换到已有分支
git diff							# 查看尚未提交的具体改动
git add <file_path>					# 添加要提交的文件；不建议直接 git add .
git commit -m "describe change"		# 提交本次修改
git push -u origin <branch_name>	# 把自己的分支推送到 GitHub
```



## 5. 推荐工作流

```bash
# 每天开始前，先更新 main：
git switch main
git pull

# 为自己的任务新建分支：
git switch -c docs-my-task

# 修改文件后检查状态：
git status
git diff

# 只添加这次要提交的文件：
git add <file_path>

# 提交并推送：
git commit -m "docs: describe my change"
git push -u origin docs-my-task
```

然后到 GitHub 页面创建 Pull Request，通知负责人审核。成员不要自己合并到 `main`。

创建 Pull Request 的最简单方法：push 后打开 GitHub 仓库首页，通常会出现 `Compare & pull request` 按钮；点进去，确认 base 是 `main`、compare 是自己的分支，简单写明改了什么，然后创建 PR。

推荐分支命名：

```text
docs-xxx       文档修改
data-xxx       数据整理
web-xxx        网站页面或样式
fix-xxx        修复问题
annotation-xxx 标注相关
```

推荐提交信息：

```text
docs: add archive literature readme
web: refine annotation page layout
data: update annotation snapshot
fix: correct evidence rendering bug
```



## 6. QA

### Q1：我可以随便改吗？

可以在自己的分支上大胆改、提交、推送。最终能不能进入 `main`，由负责人通过 Pull Request 审核。

### Q2：为什么不要直接改 main？

`main` 是稳定版本。多人直接改 `main` 容易互相覆盖，也容易把未完成内容推到线上或展示版本。

### Q3：出现冲突怎么办？

先运行：

```bash
git status
```

把冲突文件名和提示发给负责人，不要随手删除不懂的内容。冲突文件里常见标记是：

```text
<<<<<<< HEAD
你的版本
=======
别人的版本
>>>>>>> 分支名
```

### Q4：看不到 `Compare & pull request` 怎么办？

打开 GitHub 仓库页面，进入 `Pull requests`，选择 `New pull request`。base 选 `main`，compare 选自己的分支。

### Q5：能不能用 `git add .`？

不建议新手直接用。它会把当前目录下所有未忽略文件都加入提交，容易误加临时文件。优先使用：

```bash
git add 具体文件路径
```
