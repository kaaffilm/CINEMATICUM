import Cocoa

// Repository-owned vector artwork. Every installed app gets the same icon;
// no network asset, generated bitmap or external application branding.
func drawIcon(_ size: Int, at destination: URL) throws {
    guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size,
        pixelsHigh: size, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
        isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0),
        let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
        throw NSError(domain: "CINEMATICUM.Icon", code: 1)
    }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    context.imageInterpolation = .high
    context.shouldAntialias = true
    let scale = CGFloat(size) / 1024
    let transform = NSAffineTransform()
    transform.scale(by: scale)
    transform.concat()
    let panel = NSBezierPath(roundedRect: NSRect(x: 64, y: 64, width: 896, height: 896),
                             xRadius: 200, yRadius: 200)
    NSGradient(starting: NSColor(calibratedRed: 0.18, green: 0.19, blue: 0.20, alpha: 1),
               ending: NSColor(calibratedRed: 0.035, green: 0.045, blue: 0.055, alpha: 1))!
        .draw(in: panel, angle: -90)
    NSColor(calibratedWhite: 0.35, alpha: 0.45).setStroke()
    panel.lineWidth = 4
    panel.stroke()
    let mark = NSBezierPath()
    mark.appendArc(withCenter: NSPoint(x: 493, y: 512), radius: 252,
                   startAngle: 43, endAngle: 317, clockwise: false)
    mark.lineWidth = 115
    mark.lineCapStyle = .butt
    NSColor(calibratedRed: 0.88, green: 0.72, blue: 0.39, alpha: 1).setStroke()
    mark.stroke()
    let blade = NSBezierPath()
    blade.move(to: NSPoint(x: 456, y: 377))
    blade.line(to: NSPoint(x: 456, y: 647))
    blade.line(to: NSPoint(x: 682, y: 512))
    blade.close()
    NSColor(calibratedRed: 0.96, green: 0.94, blue: 0.87, alpha: 1).setFill()
    blade.fill()
    NSGraphicsContext.restoreGraphicsState()
    guard let png = bitmap.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "CINEMATICUM.Icon", code: 2)
    }
    try png.write(to: destination, options: .atomic)
}

guard CommandLine.arguments.count == 2 else { exit(2) }
do {
    let folder = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    for base in [16, 32, 128, 256, 512] {
        try drawIcon(base, at: folder.appendingPathComponent("icon_\(base)x\(base).png"))
        try drawIcon(base * 2, at: folder.appendingPathComponent("icon_\(base)x\(base)@2x.png"))
    }
} catch {
    fputs("Icon build failed: \(error)\n", stderr)
    exit(1)
}
