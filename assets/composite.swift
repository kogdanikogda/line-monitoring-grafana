// Composite the operator (generated on a green background) into the empty camera frame.
// Usage: swift composite.swift <background.png> <operator-green.png> <out.png> <feetX> <feetY> <height>
import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

func load(_ path: String) -> CGImage {
    let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil)!
    return CGImageSourceCreateImageAtIndex(src, 0, nil)!
}

func rgba(_ img: CGImage) -> (CGContext, UnsafeMutablePointer<UInt8>) {
    let w = img.width, h = img.height
    let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                        space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
    return (ctx, ctx.data!.bindMemory(to: UInt8.self, capacity: w * h * 4))
}

let a = CommandLine.arguments
let bg = load(a[1]), op = load(a[2]), out = a[3]
let feetX = Double(a[4])!, feetY = Double(a[5])!, height = Double(a[6])!

// 1) chroma key: green -> transparent, soft edge, remove green spill
let (octx, p) = rgba(op)
let w = op.width, h = op.height
var minX = w, minY = h, maxX = 0, maxY = 0
for y in 0..<h { for x in 0..<w {
    let i = (y * w + x) * 4
    let r = Double(p[i]), g = Double(p[i + 1]), b = Double(p[i + 2])
    let k = g - max(r, b)                       // how green the pixel is
    var al = 1.0
    if k > 90 { al = 0 } else if k > 30 { al = 1 - (k - 30) / 60 }
    let g2 = min(g, max(r, b) + 8)              // despill
    p[i] = UInt8(r * al); p[i + 1] = UInt8(g2 * al); p[i + 2] = UInt8(b * al); p[i + 3] = UInt8(255 * al)
    if al > 0.5 { minX = min(minX, x); maxX = max(maxX, x); minY = min(minY, y); maxY = max(maxY, y) }
} }
let keyed = octx.makeImage()!
// CGContext origin is bottom-left; pixel rows above were top-down in memory
let crop = keyed.cropping(to: CGRect(x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1))!

// 2) draw background, a soft floor shadow, then the operator scaled to `height` with feet at (feetX, feetY) (top-left coords)
let (bctx, _) = rgba(bg)
let H = Double(bg.height)
let scale = height / Double(crop.height)
let ow = Double(crop.width) * scale
bctx.saveGState()
bctx.setFillColor(CGColor(red: 0, green: 0, blue: 0, alpha: 0.28))
bctx.setShadow(offset: .zero, blur: 10, color: CGColor(red: 0, green: 0, blue: 0, alpha: 0.4))
bctx.fillEllipse(in: CGRect(x: feetX - ow * 0.45, y: H - feetY - 7, width: ow * 0.9, height: 14))
bctx.restoreGState()
bctx.interpolationQuality = .high
bctx.setAlpha(0.97)
bctx.draw(crop, in: CGRect(x: feetX - ow / 2, y: H - feetY, width: ow, height: height))
let img = bctx.makeImage()!
let dst = CGImageDestinationCreateWithURL(URL(fileURLWithPath: out) as CFURL, UTType.png.identifier as CFString, 1, nil)!
CGImageDestinationAddImage(dst, img, nil)
CGImageDestinationFinalize(dst)
print("ok", Int(ow), Int(height))
