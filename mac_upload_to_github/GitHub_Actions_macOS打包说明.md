# 使用 GitHub Actions 打包 macOS app

当前 Windows 电脑不能通过 Python 虚拟环境生成 macOS 原生 `OA_Review.app`。要自动打包并验证，可以把本目录内容上传到 GitHub 仓库，然后使用 `.github/workflows/build-macos.yml` 在 GitHub 的 macOS runner 上构建。

## 使用步骤

1. 新建一个 GitHub 仓库。
2. 把 `C:\Users\19844\Desktop\mac` 里的文件上传到仓库根目录。
3. 如果要做 A1689 数据验证，也把完整 `A1689/vis_table.csv` 和 `A1689/annotation_check_triplets/` 上传进去；不上传也可以，只会跳过数据 smoke test。
4. 在 GitHub 仓库页面打开 `Actions`。
5. 选择 `Build OA Review macOS`。
6. 点击 `Run workflow`。
7. 构建成功后，在 workflow run 的 `Artifacts` 里下载 `OA_Review-macos-app`。
8. 解压后得到 `OA_Review.app`，把它放到包含 `vis_table.csv` 和 `annotation_check_triplets` 的数据目录里运行。

## workflow 会验证什么

- 安装 `requirements-oa-review.txt` 中的依赖。
- 编译检查 `oa_review_gui.py`、`oa_review_launcher.py`、`OA_Review_macos.spec`。
- 验证 `tkinter` 和 `Pillow` 可以导入。
- 如果仓库里有 A1689 数据，则验证能加载候选记录。
- 运行 PyInstaller 构建 `dist/OA_Review.app`。
- 执行 `dist/OA_Review.app/Contents/MacOS/OA_Review --help`，确认 app 的可执行入口能启动。
- 上传 `OA_Review-macos-app.zip`。

## 注意

这个方式使用的是真实 macOS runner，不是 Windows 上的虚拟环境。它能生成 macOS `.app`，但最终 GUI 交互仍建议在真实 Mac 上打开确认一次。
