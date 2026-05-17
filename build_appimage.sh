#!/bin/bash
# Kalem — Gömülü AppImage Build Script (python + PyQt5 dahil)
# Kullanım: kalem.py ile aynı klasörde çalıştır → ./build_appimage.sh
# Gereksinim: internet bağlantısı (ilk çalıştırmada araçları indirir)
set -e

NAME="Kalem"
VERSION="0.1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORK="/tmp/kalem-build"
DIST="$WORK/dist"
APPDIR="$WORK/${NAME}.AppDir"
OUTPUT="$SCRIPT_DIR/${NAME}-${VERSION}-x86_64.AppImage"

echo "╔══════════════════════════════════════╗"
echo "║   Kalem AppImage Builder v0.1   ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 0. Kaynak dosya kontrolü ─────────────────────────────────────────
if [ ! -f "$SCRIPT_DIR/kalem.py" ]; then
    echo "✗ kalem.py bulunamadı!"
    exit 1
fi

# ── 1. Bağımlılıklar ─────────────────────────────────────────────────
echo "→ [1/5] Araçlar kontrol ediliyor..."

# PyInstaller
if ! python3 -m PyInstaller --version &>/dev/null; then
    echo "  PyInstaller kuruluyor..."
    pip3 install pyinstaller --break-system-packages 2>/dev/null \
        || pip3 install pyinstaller
fi
echo "  ✓ PyInstaller $(python3 -m PyInstaller --version)"

# PyQt5
if ! python3 -c "import PyQt5" &>/dev/null; then
    echo "  PyQt5 kuruluyor..."
    pip3 install PyQt5 --break-system-packages 2>/dev/null \
        || pip3 install PyQt5
fi
echo "  ✓ PyQt5 mevcut"

# squashfs-tools ve xvfb
for pkg in squashfs-tools xvfb; do
    if ! dpkg -l "$pkg" &>/dev/null; then
        echo "  $pkg kuruluyor..."
        sudo apt-get install -y "$pkg" -qq
    fi
done
echo "  ✓ squashfs-tools, xvfb mevcut"

# appimagetool
TOOL="$SCRIPT_DIR/appimagetool"
if [ ! -s "$TOOL" ]; then
    echo "  appimagetool indiriliyor..."
    wget -q --show-progress \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" \
        -O "$TOOL"
    chmod +x "$TOOL"
fi
echo "  ✓ appimagetool mevcut"

# ── 2. PyInstaller ile Python + PyQt5 gömme ──────────────────────────
echo ""
echo "→ [2/5] Python + PyQt5 paketleniyor (bu birkaç dakika sürebilir)..."

rm -rf "$WORK"
mkdir -p "$WORK"
cp "$SCRIPT_DIR/kalem.py" "$WORK/kalem.py"

# PNG ikonları varsa kopyala
for png in pen.png finger.png eraser.png clear.png quit.png; do
    [ -f "$SCRIPT_DIR/$png" ] && cp "$SCRIPT_DIR/$png" "$WORK/$png"
done

cd "$WORK"
python3 -m PyInstaller kalem.py \
    --name kalem \
    --onedir \
    --noconsole \
    --noconfirm \
    --distpath "$DIST" \
    --workpath "$WORK/pyinst-work" \
    --hidden-import PyQt5.QtCore \
    --hidden-import PyQt5.QtGui \
    --hidden-import PyQt5.QtWidgets \
    --hidden-import PyQt5.sip \
    --exclude-module tkinter \
    --exclude-module matplotlib \
    --exclude-module numpy \
    --exclude-module PIL \
    --exclude-module scipy \
    2>&1 | grep -E "^(INFO|ERROR|WARNING): (Building|Copying|completed|ERROR)" || true

echo "  ✓ PyInstaller tamamlandı: $(du -sh $DIST/kalem | cut -f1)"

# ── 3. AppDir oluştur ────────────────────────────────────────────────
echo ""
echo "→ [3/5] AppDir hazırlanıyor..."

mkdir -p "$APPDIR/usr/bin"

# PyInstaller çıktısını AppDir içine taşı
cp -r "$DIST/kalem" "$APPDIR/usr/bin/kalem_bundle"

# PNG ikonları da bundle içine kopyala (uygulama çalışınca bulabilsin)
for png in pen.png finger.png eraser.png clear.png quit.png; do
    [ -f "$WORK/$png" ] && cp "$WORK/$png" "$APPDIR/usr/bin/kalem_bundle/$png"
done

# AppRun
cat > "$APPDIR/AppRun" << 'APPRUN'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE=$(dirname "$SELF")
# Qt platform ayarı
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
# İkon dosyaları için PATH
export KALEM_ASSETS="$HERE/usr/bin/kalem_bundle"
exec "$HERE/usr/bin/kalem_bundle/kalem" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# .desktop
cat > "$APPDIR/kalem.desktop" << 'DESKTOP'
[Desktop Entry]
Name=Kalem
GenericName=Ekran Çizim Aracı
Comment=Ekran üzerine şeffaf katmanda çizim yap
Exec=AppRun
Icon=kalem
Terminal=false
Type=Application
Categories=Utility;Graphics;Education;
Keywords=çizim;ekran;kalem;drawing;screen;pen;
DESKTOP

# İkon: PNG varsa kullan, yoksa SVG
if [ -f "$SCRIPT_DIR/pen.png" ]; then
    cp "$SCRIPT_DIR/pen.png" "$APPDIR/kalem.png"
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

echo "  ✓ AppDir: $(du -sh $APPDIR | cut -f1)"

# ── 4. AppImage oluştur ──────────────────────────────────────────────
echo ""
echo "→ [4/5] AppImage oluşturuluyor..."

# appimagetool görsel display gerektirir → Xvfb ile çalıştır
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 xvfb-run -a \
    "$TOOL" --no-appstream \
    "$APPDIR" "$OUTPUT" 2>&1

# ── 5. Sonuç ────────────────────────────────────────────────────────
echo ""
if [ -f "$OUTPUT" ] && [ -s "$OUTPUT" ]; then
    chmod +x "$OUTPUT"
    SIZE=$(du -sh "$OUTPUT" | cut -f1)
    echo "→ [5/5] Temizleniyor..."
    rm -rf "$WORK"
    echo ""
    echo "╔══════════════════════════════════════╗"
    echo "║           Başarılı! ✓               ║"
    echo "╚══════════════════════════════════════╝"
    echo ""
    echo "  Dosya : $OUTPUT"
    echo "  Boyut : $SIZE"
    echo ""
    echo "  Çalıştır    : ./${NAME}-${VERSION}-x86_64.AppImage"
    echo "  Taşınabilir : USB'ye kopyala, her Linux'ta çalışır"
    echo "  Kaldır      : dosyayı sil, başka bir şey gerekmez"
    echo ""
else
    echo "✗ AppImage oluşturulamadı!"
    echo "  Log için: APPIMAGE_EXTRACT_AND_RUN=1 xvfb-run -a $TOOL --no-appstream $APPDIR $OUTPUT"
    exit 1
fi