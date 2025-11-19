
export interface LogSegment {
  text: string;
  type: 'cli' | 'log';
}

export class LogParser {
  private buffer: string = '';
  private onCliOutput: (text: string) => void;
  private onMonitorOutput: (text: string) => void;

  // Regex patterns
  private static readonly LOG_LINE_RE = /^([EWIDV]) \((\d+)\) ([^:]+): (.*)$/;
  // eslint-disable-next-line no-control-regex
  private static readonly ANSI_PREFIX_RE = /^(?:\x1b\[[0-9;]*m)+/;
  private static readonly LOG_PREFIXES = ['E (', 'W (', 'I (', 'D (', 'V ('];
  private static readonly SUPPRESSED_MONITOR_TAGS = new Set(['FUSION', 'MOTION', 'FLEX', 'RSSI']);

  constructor(
    onCliOutput: (text: string) => void,
    onMonitorOutput: (text: string) => void
  ) {
    this.onCliOutput = onCliOutput;
    this.onMonitorOutput = onMonitorOutput;
  }

  public feed(chunk: string): void {
    if (!chunk) return;
    this.buffer += chunk;

    while (true) {
      const newlineIdx = this.findNextNewline(this.buffer);
      if (newlineIdx === -1) break;

      const line = this.buffer.substring(0, newlineIdx);
      const consume = this.consumeNewline(this.buffer, newlineIdx);
      this.buffer = this.buffer.substring(consume);

      this.handleLine(line);
    }

    // Flush buffer if it gets too large to prevent memory issues
    if (this.buffer.length > 4096) {
      this.flushFragment(this.buffer);
      this.buffer = '';
    }
  }

  private findNextNewline(buffer: string): number {
    const n = buffer.indexOf('\n');
    const r = buffer.indexOf('\r');
    if (n === -1 && r === -1) return -1;
    if (n === -1) return r;
    if (r === -1) return n;
    return Math.min(n, r);
  }

  private consumeNewline(buffer: string, index: number): number {
    let consume = index + 1;
    if (buffer[index] === '\r' && consume < buffer.length && buffer[consume] === '\n') {
      consume++;
    }
    return consume;
  }

  private handleLine(line: string): void {
    const stripped = line.replace(/[\r\n]+$/, '');
    if (!stripped) return;
    
    const segments = this.splitLine(stripped);
    this.emitSegments(segments);
  }

  private flushFragment(fragment: string): void {
    const frag = fragment.replace(/[\r\n]+$/, '');
    if (!frag) return;
    const segments = this.splitLine(frag);
    this.emitSegments(segments);
  }

  private splitLine(text: string): LogSegment[] {
    const segments: LogSegment[] = [];
    if (!text) return segments;

    const ansiMatch = text.match(LogParser.ANSI_PREFIX_RE);
    const prefixLen = ansiMatch ? ansiMatch[0].length : 0;

    if (prefixLen > 0) {
      segments.push({ text: text.substring(0, prefixLen), type: 'cli' });
    }

    const plain = text.substring(prefixLen);
    let cursor = 0;
    const length = plain.length;

    while (cursor < length) {
      // Find the earliest occurrence of any log prefix
      let minIdx = -1;
      
      for (const prefix of LogParser.LOG_PREFIXES) {
        const idx = plain.indexOf(prefix, cursor);
        if (idx !== -1) {
          if (minIdx === -1 || idx < minIdx) {
            minIdx = idx;
          }
        }
      }

      if (minIdx === -1) {
        // No more log prefixes, the rest is CLI
        const remainder = plain.substring(cursor);
        if (remainder) {
          segments.push({ text: text.substring(prefixLen + cursor), type: 'cli' });
        }
        break;
      }

      // We found a potential log start at minIdx
      // Check if it actually matches the full log regex
      const candidate = plain.substring(minIdx);
      const match = candidate.match(LogParser.LOG_LINE_RE);

      if (!match) {
        cursor = minIdx + 1;
        continue;
      }

      // It IS a match.
      // Everything before minIdx is CLI.
      if (minIdx > cursor) {
        const cliSlice = text.substring(prefixLen + cursor, prefixLen + minIdx);
        if (cliSlice) {
          segments.push({ text: cliSlice, type: 'cli' });
        }
      }

      const logLen = match[0].length;
      const logSlice = text.substring(prefixLen + minIdx, prefixLen + minIdx + logLen);
      segments.push({ text: logSlice, type: 'log' });
      
      cursor = minIdx + logLen;
    }

    return segments;
  }

  private emitSegments(segments: LogSegment[]): void {
    for (const segment of segments) {
      if (!segment.text) continue;

      if (segment.type === 'log') {
        const plainLog = this.stripAnsi(segment.text);
        const match = plainLog.match(LogParser.LOG_LINE_RE);
        
        if (match) {
          const tag = match[3].trim().toUpperCase();
          
          // Monitor queue logic
          if (!LogParser.SUPPRESSED_MONITOR_TAGS.has(tag)) {
            this.onMonitorOutput(segment.text + '\n');
          }
          
          // CLI queue logic (if we wanted to filter logs shown in CLI, we would do it here)
          // The python code says: if self._log_filter.allows(match): self._cli_queue.put(text + "\n")
          // The user request says: "extract the cli text and sink everything else"
          // But dashboard.py allows logs in CLI if --show-logs is on.
          // The user said: "isolate just the cli relevant stuff from the stream in order to function as a cli."
          // "apply this same filtering to extract the cli text and sink everything else."
          // This implies we probably DON'T want logs in the CLI pane by default.
          // So I will NOT put logs in CLI pane.
        } else {
            // Should not happen if regex matched in splitLine, but for safety:
            this.onCliOutput(segment.text);
        }
      } else {
        // CLI segment
        this.onCliOutput(segment.text);
      }
    }
  }

  private stripAnsi(text: string): string {
    // A simple ANSI strip regex
    // eslint-disable-next-line no-control-regex
    return text.replace(/\x1b\[[0-9;]*m/g, '');
  }
}
