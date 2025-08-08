import type { Plugin } from 'drizzle-kit';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

export interface PythonGeneratorOptions {
  output: string;
  watch?: boolean;
}

export function pythonGenerator(options: PythonGeneratorOptions): Plugin {
  return {
    name: 'drizzle-python-generator',

    // Hook into Drizzle Kit's lifecycle
    async onGenerate() {
      console.log('🐍 Generating Python models from Drizzle schemas...');

      try {
        // Run the generator script
        execSync('tsx scripts/drizzle-to-python.ts', {
          stdio: 'inherit',
          cwd: process.cwd()
        });



        console.log('✅ Python models generated successfully!');
      } catch (error) {
        console.error('❌ Failed to generate Python models:', error);
        throw error;
      }
    },

    // Watch mode support
    async onWatch() {
      if (options.watch) {
        console.log('👀 Watching for schema changes...');

        // Set up file watcher for schema directory
        const schemaDir = path.join(process.cwd(), 'src/lib/db/schema');

        fs.watch(schemaDir, { recursive: true }, (eventType, filename) => {
          if (filename?.endsWith('.ts') && filename !== 'index.ts') {
            console.log(`📝 Schema file changed: ${filename}`);
            this.onGenerate();
          }
        });
      }
    }
  };
}
