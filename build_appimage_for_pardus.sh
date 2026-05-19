#!/bin/bash
# Kalem — AppImage Build Script
# Pardus ETAP (Debian 12) hedefli — pyenv ile Python 3.11 kullanır
# Kullanım: kalem.py ile aynı klasörde → bash build_appimage.sh

set -e

NAME="Kalem"
VERSION="0.1"
PYTHON_VERSION="3.11.9"        # Debian 12 / Pardus ETAP ile uyumlu
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORK="/tmp/kalem-build"
APPDIR="$WORK/${NAME}.AppDir"
OUTPUT="$SCRIPT_DIR/${NAME}-${VERSION}-x86_64.AppImage"
TOOL="$SCRIPT_DIR/appimagetool"
PYENV_ROOT="$HOME/.pyenv"
PYTHON_BIN="$PYENV_ROOT/versions/$PYTHON_VERSION/bin/python3"

echo "╔══════════════════════════════════════╗"
echo "║     Kalem AppImage Builder v0.1     ║"
echo "║  Hedef: Debian 12 / Pardus ETAP     ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 0. Kaynak dosya kontrolü ─────────────────────────────────────────
if [ ! -f "$SCRIPT_DIR/kalem.py" ]; then
    echo "✗ kalem.py bulunamadı!"; exit 1
fi
echo "✓ kalem.py bulundu"

# ── 1. Build bağımlılıkları ──────────────────────────────────────────
echo ""
echo "→ [1/5] Sistem paketleri kontrol ediliyor..."

MISSING=""
for pkg in squashfs-tools xvfb wget curl git \
           build-essential libssl-dev zlib1g-dev \
           libbz2-dev libreadline-dev libsqlite3-dev \
           libncursesw5-dev xz-utils tk-dev libxml2-dev \
           libxmlsec1-dev libffi-dev liblzma-dev; do
    dpkg -l "$pkg" &>/dev/null || MISSING="$MISSING $pkg"
done

if [ -n "$MISSING" ]; then
    echo "  Eksik paketler kuruluyor:$MISSING"
    sudo apt-get install -y $MISSING -qq
fi
echo "  ✓ Sistem paketleri tamam"

# ── 2. pyenv + Python 3.11 ───────────────────────────────────────────
echo ""
echo "→ [2/5] Python $PYTHON_VERSION kontrol ediliyor..."

# pyenv kur (yoksa)
if [ ! -d "$PYENV_ROOT" ]; then
    echo "  pyenv kuruluyor..."
    curl -fsSL https://pyenv.run | bash
fi

# pyenv'i PATH'e ekle
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

# Python 3.11.9 kur (yoksa)
if [ ! -f "$PYTHON_BIN" ]; then
    echo "  Python $PYTHON_VERSION derleniyor (5-10 dk sürebilir)..."
    pyenv install $PYTHON_VERSION
fi
echo "  ✓ Python $($PYTHON_BIN --version)"

# PyQt5 ve PyInstaller kur (bu Python için)
PIP="$PYENV_ROOT/versions/$PYTHON_VERSION/bin/pip3"
echo "  PyQt5 + PyInstaller kuruluyor..."
$PIP install --quiet PyQt5 pyinstaller

echo "  ✓ PyQt5 $($PYTHON_BIN -c 'import PyQt5.QtCore; print(PyQt5.QtCore.PYQT_VERSION_STR)')"
echo "  ✓ PyInstaller $($PYTHON_BIN -m PyInstaller --version)"

# ── 3. appimagetool ──────────────────────────────────────────────────
echo ""
echo "→ [3/5] appimagetool kontrol ediliyor..."
if [ ! -s "$TOOL" ]; then
    echo "  İndiriliyor..."
    wget -q --show-progress \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" \
        -O "$TOOL"
    chmod +x "$TOOL"
fi
echo "  ✓ appimagetool hazır"

# ── 4. PyInstaller ile paketle ───────────────────────────────────────
echo ""
echo "→ [4/5] Python $PYTHON_VERSION ile paketleniyor..."

rm -rf "$WORK"
mkdir -p "$WORK"
cp "$SCRIPT_DIR/kalem.py" "$WORK/kalem.py"
for png in pen.png finger.png eraser.png clear.png quit.png; do
    [ -f "$SCRIPT_DIR/$png" ] && cp "$SCRIPT_DIR/$png" "$WORK/$png"
done

cd "$WORK"

PYINSTALLER="$PYENV_ROOT/versions/$PYTHON_VERSION/bin/pyinstaller"
PYQT5_PATH=$($PYTHON_BIN -c "import PyQt5, os; print(os.path.dirname(PyQt5.__file__))")

$PYINSTALLER kalem.py \
    --name kalem \
    --onedir \
    --noconsole \
    --noconfirm \
    --distpath "$WORK/dist" \
    --workpath "$WORK/build" \
    --hidden-import PyQt5.QtCore \
    --hidden-import PyQt5.QtGui \
    --hidden-import PyQt5.QtWidgets \
    --hidden-import PyQt5.sip \
    --paths "$PYQT5_PATH" \
    --exclude-module tkinter \
    --exclude-module matplotlib \
    --exclude-module numpy \
    --exclude-module PIL \
    --exclude-module scipy \
    2>&1 | grep -E "(Building|completed successfully|ERROR)" || true

echo "  ✓ Paketlendi: $(du -sh $WORK/dist/kalem | cut -f1)"

# ── 5. AppDir + AppImage ─────────────────────────────────────────────
echo ""
echo "→ [5/5] AppImage oluşturuluyor..."

mkdir -p "$APPDIR/usr/bin"
cp -r "$WORK/dist/kalem" "$APPDIR/usr/bin/kalem_bundle"

for png in pen.png finger.png eraser.png clear.png quit.png; do
    [ -f "$WORK/$png" ] && cp "$WORK/$png" "$APPDIR/usr/bin/kalem_bundle/$png"
done

cat > "$APPDIR/AppRun" << 'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
exec "$HERE/usr/bin/kalem_bundle/kalem" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

cat > "$APPDIR/kalem.desktop" << 'DESKTOP'
[Desktop Entry]
Name=Kalem
Comment=Ekran üzerine çizim yap
Exec=AppRun
Icon=kalem
Terminal=false
Type=Application
Categories=Utility;Graphics;
DESKTOP

if [ -f "$WORK/pen.png" ]; then
    cp "$WORK/pen.png" "$APPDIR/kalem.png"
else
    cat > "$APPDIR/kalem.svg" << 'SVG'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect width="64" height="64" rx="12" fill="#2d2d2d"/>
  <line x1="16" y1="48" x2="48" y2="16" stroke="#00ffff" stroke-width="5" stroke-linecap="round"/>
  <circle cx="48" cy="16" r="5" fill="#00ffff"/>
  <polygon points="14,50 10,54 18,54" fill="#888"/>
</svg>
SVG
fi

ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 xvfb-run -a \
    "$TOOL" --no-appstream "$APPDIR" "$OUTPUT" 2>&1

# ── Sonuç ────────────────────────────────────────────────────────────
echo ""
if [ -f "$OUTPUT" ] && [ -s "$OUTPUT" ]; then
    chmod +x "$OUTPUT"
    SIZE=$(du -sh "$OUTPUT" | cut -f1)
    rm -rf "$WORK"
    echo "╔══════════════════════════════════════╗"
    echo "║           Başarılı! ✓               ║"
    echo "╚══════════════════════════════════════╝"
    echo ""
    echo "  Dosya : $OUTPUT"
    echo "  Boyut : $SIZE"
    echo ""
    echo "  Pardus ETAP'ta çalıştır:"
    echo "  ./Kalem-0.1-x86_64.AppImage"
else
    echo "✗ AppImage oluşturulamadı!"
    exit 1
fi