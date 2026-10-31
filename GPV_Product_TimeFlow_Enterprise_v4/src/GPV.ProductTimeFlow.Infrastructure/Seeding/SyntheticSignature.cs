using System.IO.Compression;
using System.Text;

namespace GPV.ProductTimeFlow.Infrastructure.Seeding;

/// <summary>
/// Genera una imagen PNG de firma SINTÉTICA (trazo ondulado) para los datos de demostración y pruebas.
/// No representa la firma de ninguna persona real.
/// </summary>
public static class SyntheticSignature
{
    public static byte[] Create(int seed, int width = 360, int height = 120)
    {
        var pixels = new byte[width * height];
        Array.Fill(pixels, (byte)255);
        var rnd = new Random(seed);
        double a1 = 18 + rnd.NextDouble() * 14, f1 = 0.035 + rnd.NextDouble() * 0.03, p1 = rnd.NextDouble() * 6;
        double a2 = 6 + rnd.NextDouble() * 8, f2 = 0.11 + rnd.NextDouble() * 0.06;
        (double X, double Y)? prev = null;
        for (var x = 20; x < width - 20; x++)
        {
            var y = height / 2.0 + a1 * Math.Sin(x * f1 + p1) + a2 * Math.Sin(x * f2) * Math.Exp(-x / (double)width);
            if (prev is { } p) Line(pixels, width, height, p.X, p.Y, x, y);
            prev = (x, y);
        }
        Line(pixels, width, height, 40, height - 22, width - 60, height - 26);
        return EncodeGrayscalePng(pixels, width, height);
    }

    private static void Line(byte[] px, int w, int h, double x0, double y0, double x1, double y1)
    {
        var steps = (int)Math.Max(Math.Abs(x1 - x0), Math.Abs(y1 - y0)) * 2 + 1;
        for (var i = 0; i <= steps; i++)
        {
            var x = x0 + (x1 - x0) * i / steps;
            var y = y0 + (y1 - y0) * i / steps;
            for (var dx = -1; dx <= 1; dx++)
            for (var dy = -1; dy <= 1; dy++)
            {
                int xi = (int)x + dx, yi = (int)y + dy;
                if (xi >= 0 && xi < w && yi >= 0 && yi < h) px[yi * w + xi] = 30;
            }
        }
    }

    private static byte[] EncodeGrayscalePng(byte[] pixels, int width, int height)
    {
        using var raw = new MemoryStream();
        for (var y = 0; y < height; y++) { raw.WriteByte(0); raw.Write(pixels, y * width, width); }
        using var compressed = new MemoryStream();
        using (var z = new ZLibStream(compressed, CompressionLevel.Optimal, leaveOpen: true)) { raw.Position = 0; raw.CopyTo(z); }

        using var png = new MemoryStream();
        png.Write([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);
        var ihdr = new byte[13];
        WriteBE(ihdr, 0, (uint)width); WriteBE(ihdr, 4, (uint)height);
        ihdr[8] = 8; ihdr[9] = 0; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
        Chunk(png, "IHDR", ihdr);
        Chunk(png, "IDAT", compressed.ToArray());
        Chunk(png, "IEND", []);
        return png.ToArray();
    }

    private static void Chunk(Stream s, string type, byte[] data)
    {
        var len = new byte[4]; WriteBE(len, 0, (uint)data.Length); s.Write(len);
        var typeBytes = Encoding.ASCII.GetBytes(type);
        s.Write(typeBytes); s.Write(data);
        var crc = Crc32(typeBytes.Concat(data).ToArray());
        var c = new byte[4]; WriteBE(c, 0, crc); s.Write(c);
    }

    private static void WriteBE(byte[] b, int o, uint v) { b[o] = (byte)(v >> 24); b[o + 1] = (byte)(v >> 16); b[o + 2] = (byte)(v >> 8); b[o + 3] = (byte)v; }

    private static uint Crc32(byte[] data)
    {
        var crc = 0xFFFFFFFFu;
        foreach (var b in data)
        {
            crc ^= b;
            for (var k = 0; k < 8; k++) crc = (crc & 1) != 0 ? 0xEDB88320u ^ (crc >> 1) : crc >> 1;
        }
        return ~crc;
    }

    public static string Base64(int seed) => Convert.ToBase64String(Create(seed));
}
