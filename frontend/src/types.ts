export type Status = 'idle' | 'transcribing' | 'reviewing' | 'translating' | 'translated' | 'dubbing' | 'finished';

export interface Segment {
    id: string;
    start: number;
    end: number;
    text: string;
}
