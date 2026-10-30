import { endpoints } from "./api";

type ExportRow = unknown[];
type DocxModule = typeof import("docx");

const pageWidth = 14400;

async function loadPng(source: string) {
  const image = new Image();
  image.src = source;
  await image.decode();
  const scale = Math.min(1, 320 / image.naturalWidth, 100 / image.naturalHeight);
  const width = Math.max(1, Math.round(image.naturalWidth * scale));
  const height = Math.max(1, Math.round(image.naturalHeight * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("The report logo could not be prepared.");
  context.drawImage(image, 0, 0, width, height);
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((result) => result ? resolve(result) : reject(new Error("The report logo could not be prepared.")), "image/png");
  });
  return { data: new Uint8Array(await blob.arrayBuffer()), width, height };
}

function imageRun(image: Awaited<ReturnType<typeof loadPng>>, docx: DocxModule, maxWidth: number, maxHeight: number) {
  const scale = Math.min(maxWidth / image.width, maxHeight / image.height, 1);
  return new docx.ImageRun({
    data: image.data,
    type: "png",
    transformation: { width: Math.max(1, image.width * scale), height: Math.max(1, image.height * scale) },
    altText: { title: "HIOP report logo", description: "HIOP", name: "HIOP logo" },
  });
}

function asText(value: unknown) {
  if (value === null || value === undefined) return "";
  return String(value);
}

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let value = "";
  let quoted = false;
  for (let index = text.charCodeAt(0) === 0xfeff ? 1 : 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') {
        value += '"';
        index += 1;
      } else if (character === '"') {
        quoted = false;
      } else {
        value += character;
      }
    } else if (character === '"' && value === "") {
      quoted = true;
    } else if (character === ",") {
      row.push(value);
      value = "";
    } else if (character === "\n" || character === "\r") {
      if (character === "\r" && text[index + 1] === "\n") index += 1;
      row.push(value);
      if (row.some((cell) => cell !== "")) rows.push(row);
      row = [];
      value = "";
    } else {
      value += character;
    }
  }
  if (quoted) throw new Error("The CSV export contains an unterminated quoted field.");
  if (value !== "" || row.length) {
    row.push(value);
    if (row.some((cell) => cell !== "")) rows.push(row);
  }
  return rows;
}

function makeTable(rows: ExportRow[], docx: DocxModule) {
  const data = rows.length ? rows : [["No data available"]];
  const columnCount = Math.max(1, ...data.map((row) => row.length));
  const headings = data[0].map((value) => asText(value).toLowerCase());
  const weights = Array.from({ length: columnCount }, (_, index) => {
    const heading = headings[index] ?? "";
    if (/^(asset number|asset tag|ip address|mac address|device type|status|health|warranty status)$/.test(heading)) return 0.7;
    if (/^(name|hostname|assigned to|department|location|vendor|model|serial number)$/.test(heading)) return 1.25;
    return 1;
  });
  const totalWeight = weights.reduce((sum, weight) => sum + weight, 0);
  const columnWidths = weights.map((weight) => Math.floor(pageWidth * weight / totalWeight));
  columnWidths[columnCount - 1] += pageWidth - columnWidths.reduce((sum, width) => sum + width, 0);
  const border = { style: docx.BorderStyle.SINGLE, size: 1, color: "D8E0EA" };
  const tableBorders = { top: border, bottom: border, left: border, right: border, insideHorizontal: border, insideVertical: border };
  const tableRows = data.map((row, rowIndex) => {
    const cells = Array.from({ length: columnCount }, (_, columnIndex) => {
      const isHeading = rowIndex === 0;
      const lines = asText(row[columnIndex]).split(/\r?\n/);
      return new docx.TableCell({
        width: { size: columnWidths[columnIndex], type: docx.WidthType.DXA },
        borders: tableBorders,
        shading: isHeading
          ? { type: docx.ShadingType.CLEAR, color: "FFFFFF", fill: "17365D" }
          : rowIndex % 2 === 0
            ? { type: docx.ShadingType.CLEAR, color: "FFFFFF", fill: "F3F6FA" }
            : undefined,
        margins: { top: 70, bottom: 70, left: 55, right: 55 },
        children: lines.map((line) => {
          const separator = isHeading ? -1 : line.indexOf(": ");
          const label = separator >= 0 ? line.slice(0, separator + 1) : "";
          const value = separator >= 0 ? line.slice(separator + 2) : line;
          return new docx.Paragraph({
            children: [
              ...(label ? [new docx.TextRun({ text: label, bold: true, color: "526173", size: 14, font: "Aptos" })] : []),
              new docx.TextRun({
                text: value,
                bold: isHeading,
                color: isHeading ? "FFFFFF" : "263445",
                size: isHeading ? 15 : 14,
                font: "Aptos",
              }),
            ],
            spacing: { after: 25 },
          });
        }),
      });
    });
    return new docx.TableRow({ children: cells, tableHeader: rowIndex === 0, cantSplit: true });
  });
  return new docx.Table({ width: { size: pageWidth, type: docx.WidthType.DXA }, columnWidths, borders: tableBorders, rows: tableRows });
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadBrandedWordReport(title: string, filename: string, rows: ExportRow[]) {
  const docx = await import("docx");
  const organization = await endpoints.organizationProfile();
  const baseUrl = import.meta.env.BASE_URL;
  const hiopLogoUrl = `${baseUrl}hospitality-it-ops-wordmark-dark-transparent.png`;
  const hiopLogo = await loadPng(hiopLogoUrl);
  const organizationLogo = organization.logo ? await loadPng(organization.logo) : undefined;
  const generatedAt = new Date();
  const header = new docx.Header({
    children: [
      new docx.Paragraph({
        alignment: docx.AlignmentType.LEFT,
        children: [
          imageRun(hiopLogo, docx, 170, 45),
          new docx.TextRun({ text: `     ${organization.name}`, bold: true, color: "17365D", size: 24, font: "Aptos" }),
          ...(organizationLogo ? [new docx.TextRun({ text: "     " }), imageRun(organizationLogo, docx, 48, 48)] : []),
        ],
        border: { bottom: { style: docx.BorderStyle.SINGLE, size: 8, color: "1E6AA8", space: 8 } },
        spacing: { after: 120 },
      }),
    ],
  });
  const footer = new docx.Footer({
    children: [new docx.Paragraph({
      alignment: docx.AlignmentType.CENTER,
      children: [
        new docx.TextRun({ text: `${organization.name} · Generated ${generatedAt.toLocaleString()} · Page `, color: "667085", size: 16 }),
        new docx.TextRun({ children: [docx.PageNumber.CURRENT], color: "667085", size: 16 }),
      ],
    })],
  });
  const document = new docx.Document({
    creator: "HIOP",
    title,
    description: `HIOP report for ${organization.name}`,
    sections: [{
      properties: {
        page: { size: { width: 15840, height: 12240, orientation: docx.PageOrientation.LANDSCAPE }, margin: { top: 900, right: 720, bottom: 900, left: 720 } },
      },
      headers: { default: header },
      footers: { default: footer },
      children: [
        new docx.Paragraph({ children: [new docx.TextRun({ text: title, bold: true, color: "17365D", size: 34, font: "Aptos Display" })], spacing: { before: 200, after: 100 } }),
        new docx.Paragraph({ children: [new docx.TextRun({ text: `${rows.length ? Math.max(0, rows.length - 1) : 0} record(s) · Generated ${generatedAt.toLocaleString()}`, color: "667085", size: 18 })], spacing: { after: 220 } }),
        makeTable(rows, docx),
      ],
    }],
  });
  const output = await docx.Packer.toBlob(document);
  saveBlob(output, filename.replace(/\.csv$/i, "").replace(/\.docx$/i, "") + ".docx");
}

export async function downloadCsvAsBrandedWordReport(title: string, filename: string, csv: Blob) {
  const rows = parseCsv(await csv.text());
  await downloadBrandedWordReport(title, filename, rows);
}

export async function downloadExportFile(format: "csv" | "word", title: string, filename: string, blob: Blob) {
  if (format === "word") {
    await downloadCsvAsBrandedWordReport(title, filename, blob);
    return;
  }
  saveBlob(blob, filename);
}
