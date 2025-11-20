#!/bin/bash

SOURCE="assets/blecliicon.png"
IOS_DIR="ios/BLECLIApp/Images.xcassets/AppIcon.appiconset"
ANDROID_RES="android/app/src/main/res"

# iOS Sizes
# Size | Scale | Filename
# 20   | 2x    | Icon-20@2x.png
# 20   | 3x    | Icon-20@3x.png
# 29   | 2x    | Icon-29@2x.png
# 29   | 3x    | Icon-29@3x.png
# 40   | 2x    | Icon-40@2x.png
# 40   | 3x    | Icon-40@3x.png
# 60   | 2x    | Icon-60@2x.png
# 60   | 3x    | Icon-60@3x.png
# 1024 | 1x    | Icon-1024.png

mkdir -p "$IOS_DIR"

# Function to generate iOS icon
gen_ios() {
    SIZE=$1
    SCALE=$2
    NAME="Icon-$SIZE@${SCALE}x.png"
    if [ "$SCALE" == "1" ]; then
        NAME="Icon-$SIZE.png"
    fi
    
    REAL_SIZE=$(($SIZE * $SCALE))
    sips -z $REAL_SIZE $REAL_SIZE "$SOURCE" --out "$IOS_DIR/$NAME"
}

gen_ios 20 2
gen_ios 20 3
gen_ios 29 2
gen_ios 29 3
gen_ios 40 2
gen_ios 40 3
gen_ios 60 2
gen_ios 60 3
gen_ios 1024 1

# Update Contents.json
cat > "$IOS_DIR/Contents.json" <<EOF
{
  "images" : [
    {
      "size" : "20x20",
      "idiom" : "iphone",
      "filename" : "Icon-20@2x.png",
      "scale" : "2x"
    },
    {
      "size" : "20x20",
      "idiom" : "iphone",
      "filename" : "Icon-20@3x.png",
      "scale" : "3x"
    },
    {
      "size" : "29x29",
      "idiom" : "iphone",
      "filename" : "Icon-29@2x.png",
      "scale" : "2x"
    },
    {
      "size" : "29x29",
      "idiom" : "iphone",
      "filename" : "Icon-29@3x.png",
      "scale" : "3x"
    },
    {
      "size" : "40x40",
      "idiom" : "iphone",
      "filename" : "Icon-40@2x.png",
      "scale" : "2x"
    },
    {
      "size" : "40x40",
      "idiom" : "iphone",
      "filename" : "Icon-40@3x.png",
      "scale" : "3x"
    },
    {
      "size" : "60x60",
      "idiom" : "iphone",
      "filename" : "Icon-60@2x.png",
      "scale" : "2x"
    },
    {
      "size" : "60x60",
      "idiom" : "iphone",
      "filename" : "Icon-60@3x.png",
      "scale" : "3x"
    },
    {
      "size" : "1024x1024",
      "idiom" : "ios-marketing",
      "filename" : "Icon-1024.png",
      "scale" : "1x"
    }
  ],
  "info" : {
    "version" : 1,
    "author" : "xcode"
  }
}
EOF

# Android
# mdpi: 48
# hdpi: 72
# xhdpi: 96
# xxhdpi: 144
# xxxhdpi: 192

gen_android() {
    FOLDER=$1
    SIZE=$2
    mkdir -p "$ANDROID_RES/$FOLDER"
    sips -z $SIZE $SIZE "$SOURCE" --out "$ANDROID_RES/$FOLDER/ic_launcher.png"
    sips -z $SIZE $SIZE "$SOURCE" --out "$ANDROID_RES/$FOLDER/ic_launcher_round.png"
}

gen_android "mipmap-mdpi" 48
gen_android "mipmap-hdpi" 72
gen_android "mipmap-xhdpi" 96
gen_android "mipmap-xxhdpi" 144
gen_android "mipmap-xxxhdpi" 192

echo "Icons generated successfully."
