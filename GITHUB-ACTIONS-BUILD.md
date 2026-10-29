# Build the universal installer from your Intel Mac using GitHub Actions

This project contains a GitHub Actions workflow that builds the Intel app on a hosted Intel macOS runner and the Apple Silicon app on a hosted Apple Silicon macOS runner, then assembles both into one `.pkg`. You do not need to build anything on the church Mac.

## 1. Create a private GitHub repository

1. Sign in at https://github.com/new.
2. Name the repository `wing-voice-assistant` and select **Private**.
3. Create it without adding a README, `.gitignore`, or licence (the project already contains these).

## 2. Upload this project from your Intel Mac

1. Download and extract this project ZIP.
2. Open Terminal and change into the extracted `wing-voice-assistant` folder. A simple way is to type `cd ` (including the space), drag the folder into Terminal, and press Return.
3. Run the following commands, replacing `YOUR-GITHUB-USERNAME` with your GitHub username:

```bash
git init
git add .
git commit -m "Add WING Voice Assistant and universal build workflow"
git branch -M main
git remote add origin https://github.com/YOUR-GITHUB-USERNAME/wing-voice-assistant.git
git push -u origin main
```

If Git asks you to authenticate, follow GitHub's browser sign-in instructions. Never put a password or access token in the command or in this project.

## 3. Start the cloud build

1. Open your repository on GitHub.
2. Select **Actions**.
3. Select **Build WING Voice Assistant Universal Installer** in the workflow list.
4. Click **Run workflow**, keep the branch set to `main`, and click the green **Run workflow** button.
5. Wait for both architecture builds and the packaging job to finish green. The first build may take a while because it downloads Python packages and local speech models.

The workflow uses GitHub-hosted macOS runners (`macos-15-intel` and `macos-15`) so native dependencies are built on their target architectures. See GitHub's current runner documentation: https://docs.github.com/en/actions/reference/runners/github-hosted-runners.

## 4. Download the finished installer

1. Open the completed workflow run.
2. Scroll to **Artifacts** at the bottom.
3. Download `WING-Voice-Assistant-Universal-Installer` and unzip the downloaded artifact if GitHub wraps it in a ZIP.
4. The file inside should be `WING-Voice-Assistant-Universal.pkg`.
5. Copy that `.pkg` to the church Mac and run it.

The workflow artifact is retained for 14 days. Run the workflow again if it expires.

## Important notes

- This creates a **universal installer** containing separate native Intel and Apple Silicon apps. It is not a single universal2 executable.
- This is an unsigned and not notarized local installer unless you add Apple Developer ID signing and notarization. macOS may warn when opening the app. Do not bypass a warning you do not understand.
- GitHub-hosted runner availability and billing/quotas depend on repository visibility and account plan. Check https://docs.github.com/en/billing/concepts/product-billing/github-actions before repeated builds. Standard hosted runners are free for public repositories; private repositories consume included minutes and may be billed after the allowance.
- The installer does not include the separately configured WING MCP gateway or private console-specific configuration. Configure those in the GUI on the church Mac.
- This workflow verifies the architecture labels and that a package was produced; it does not prove that the assistant works with the physical WING, Dante routing, microphone permissions, or your exact MCP schemas. Test the installed app with mixer writes disabled and at low levels first. Keep all six IEM bus indices blank until verified on the actual console.
- The build can fail if a dependency changes or a native package is incompatible with the selected runner. If it fails, open the failed job, copy the first relevant error and the surrounding log, and use that to troubleshoot.
