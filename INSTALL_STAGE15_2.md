# Stage 15.2 installation

Upload `degen-detector-stage15-2-verified.zip` to the root of the GitHub Codespace, then run:

```bash
unzip -o degen-detector-stage15-2-verified.zip
python -m unittest discover -s commander_bot/tests -v
git add commander_bot STAGE15_BEGINNER_GUIDE.md STAGE15_2_VERSION.txt INSTALL_STAGE15_2.md requirements.txt
git commit -m "Install verified Stage 15.2 dual-chain update"
git push
```

The ZIP contains its files directly at the archive root. No copy command or nested folder is required.
