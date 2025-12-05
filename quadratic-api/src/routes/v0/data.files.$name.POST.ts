import { createHash } from "crypto";
import type { Response } from 'express';
import fs from "fs/promises";
import path from "path";
import type { ApiTypes } from 'quadratic-shared/typesAndSchemas';
import z from 'zod';
import { API_FILES_DIR } from "../../env-vars";
import { userMiddleware } from '../../middleware/user';
import { validateAccessToken } from '../../middleware/validateAccessToken';
import { validateRequestSchema } from '../../middleware/validateRequestSchema';
import { S3Bucket } from '../../storage/s3';
import { uploadMiddleware } from '../../storage/storage';
import type { RequestWithFile, RequestWithUser } from '../../types/Request';
import { ApiError } from '../../utils/ApiError';

async function handler(req: RequestWithUser & RequestWithFile, res: Response<ApiTypes['/v0/data/files/:name.POST.response']>) {
  try {
    const {
      params: { name },
    } = req;

    if (!req.file) {
      throw new ApiError(500, 'No file uploaded.');
    }

    const buffer = req.file.buffer;

    // 1) Compute SHA-256
    const sha256sum = createHash("sha256").update(buffer).digest("hex");

    // 2) Save file to disk
    const destPath = path.join(API_FILES_DIR, name);
    await fs.writeFile(destPath, buffer);

    return res.json({
      sha256sum,
    });
  } catch (err) {
    throw new ApiError(500, `${err}`);
  }
}

export default [
  validateRequestSchema(
    z.object({
      params: z.object({
        name: z.string(),
      }),
    })
  ),
  validateAccessToken,
  userMiddleware,
  uploadMiddleware(S3Bucket.MEMORY).single('file'),
  handler,
];
