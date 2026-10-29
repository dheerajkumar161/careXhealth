/**
 * Downscales a photo in the browser before upload: keeps text legible for the vision model
 * while turning multi-MB phone photos into a few hundred KB.
 */
export async function fileToDataUrl(file: File, maxSide = 1800, quality = 0.88): Promise<string> {
  if (!/^image\/(png|jpe?g|webp|gif)$/.test(file.type)) throw new Error(`${file.name}: use a PNG, JPEG or WebP image`);
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Image processing is not supported in this browser");
  ctx.fillStyle = "#ffffff"; // transparent PNGs → white, so text stays readable as JPEG
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return canvas.toDataURL("image/jpeg", quality);
}
