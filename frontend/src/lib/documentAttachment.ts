// Attachment payload stays inside the same signed and encrypted document envelope.
export function downloadAttachment(content: string): boolean {
  let value;
  try {
    value = JSON.parse(content);
  } catch {
    return false;
  }
  if (value?.quantumcare_attachment !== 1) return false;
  if (
    typeof value.filename !== "string" ||
    typeof value.data_base64 !== "string" ||
    ![
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ].includes(value.mime)
  )
    throw new Error("Invalid attachment envelope");
  const bytes = Uint8Array.from(atob(value.data_base64), (c) =>
    c.charCodeAt(0),
  );
  const url = URL.createObjectURL(new Blob([bytes], { type: value.mime }));
  const link = document.createElement("a");
  link.href = url;
  link.download = value.filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
  return true;
}
export async function attachmentFromFile(file: File) {
  if (file.size > 10 * 1024 * 1024 || !/\.(pdf|docx)$/i.test(file.name))
    throw new Error("Select a PDF or DOCX up to 10 MiB");
  const data = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(new Error("Unable to read file"));
    reader.readAsDataURL(file);
  });
  return { filename: file.name, data_base64: data };
}
