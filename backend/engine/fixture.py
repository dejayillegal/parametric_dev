"""Synthetic, original Live-11-schema-style fixture authored by Parametric ALS.

NOT created in Ableton Live; used to exercise the parser/validator. It intentionally
contains: 140 BPM, nested groups, a confirmed sidechain (KICK -> BASS GROUP compressor),
an automation envelope, an audio clip with an unresolved sample, an unknown plugin
device, an opaque future-version block, and two return tracks.
"""
import gzip

_aid = [1000]


def _at():
    _aid[0] += 1
    return f'<AutomationTarget Id="{_aid[0]}"><LockEnvelope Value="0" /></AutomationTarget>', _aid[0]


def _param(tag, val):
    at, i = _at()
    return f'<{tag}><LomId Value="0" /><Manual Value="{val}" />{at}</{tag}>', i


def _mixer(nsends, vol="0.7943282", pan="0", speaker="true"):
    sends = "".join(f'<TrackSendHolder Id="{k}"><Send><Manual Value="0" /></Send><Active Value="true" /></TrackSendHolder>' for k in range(nsends))
    v, _ = _param("Volume", vol)
    pn, _ = _param("Pan", pan)
    sp, _ = _param("Speaker", speaker)
    return f"<Mixer><Sends>{sends}</Sends>{sp}{v}{pn}</Mixer>"


def _notes(pitch_times, length=0.25, vel=100):
    by = {}
    for p, t in pitch_times:
        by.setdefault(p, []).append(t)
    out, nid = [], 1
    for p, ts in sorted(by.items()):
        evs = ""
        for t in ts:
            evs += f'<MidiNoteEvent Time="{t}" Duration="{length}" Velocity="{vel}" OffVelocity="64" Probability="1" IsEnabled="true" NoteId="{nid}" />'
            nid += 1
        out.append(f'<KeyTrack Id="{p}"><Notes>{evs}</Notes><MidiKey Value="{p}" /></KeyTrack>')
    return "".join(out)


def _midiclip(cid, start, end, name, notes):
    return (f'<MidiClip Id="{cid}" Time="{start}"><CurrentStart Value="{start}" /><CurrentEnd Value="{end}" />'
            f'<Loop><LoopStart Value="0" /><LoopEnd Value="16" /><StartRelative Value="0" /><LoopOn Value="true" /></Loop>'
            f'<Name Value="{name}" /><Color Value="3" /><Notes><KeyTracks>{notes}</KeyTracks></Notes></MidiClip>')


def _track(tag, tid, name, group, devices="", clips="", envelopes="", nsends=2, out="AudioOut/Main"):
    seq = f"<MainSequencer><ClipSlotList /><ClipTimeable><ArrangerAutomation><Events>{clips}</Events></ArrangerAutomation></ClipTimeable></MainSequencer>"
    return (f'<{tag} Id="{tid}"><LomId Value="0" /><Name><EffectiveName Value="{name}" /><UserName Value="{name}" /></Name>'
            f'<Color Value="{tid % 20}" /><TrackGroupId Value="{group}" />'
            f'<AutomationEnvelopes><Envelopes>{envelopes}</Envelopes></AutomationEnvelopes>'
            f'<DeviceChain><AudioOutputRouting><Target Value="{out}" /></AudioOutputRouting>'
            f'{_mixer(nsends)}{seq}<DeviceChain><Devices>{devices}</Devices></DeviceChain></DeviceChain></{tag}>')


def build_demo_xml():
    _aid[0] = 1000
    kick_notes = _notes([(36, b) for b in range(0, 64)], 0.25, 127)
    hat_notes = _notes([(42, b + 0.5) for b in range(0, 64)], 0.125, 90)
    bass_notes = _notes([(29, b + 0.25) for b in range(0, 64)] + [(29, b + 0.75) for b in range(0, 64)], 0.2, 100)
    pad_notes = _notes([(p, 64) for p in (53, 56, 60)], 16, 80)
    cutoff, cut_id = _param("Cutoff", "800")
    pad_env = (f'<AutomationEnvelope Id="0"><EnvelopeTarget><PointeeId Value="{cut_id}" /></EnvelopeTarget><Automation><Events>'
               f'<FloatEvent Id="1" Time="-63072000" Value="800" /><FloatEvent Id="2" Time="64" Value="400" />'
               f'<FloatEvent Id="3" Time="96" Value="6000" /></Events></Automation></AutomationEnvelope>')
    comp_thr, _ = _param("Threshold", "0.3")
    comp = (f'<Compressor2 Id="0"><On><Manual Value="true" /></On>{comp_thr}<SideChain><OnOff><Manual Value="true" /></OnOff>'
            f'<RoutedInput><Routable><Target Value="AudioIn/Track.11/PostFxOut" /></Routable></RoutedInput></SideChain></Compressor2>')
    op_on, _ = _param("Volume", "1")
    tempo, tempo_id = _param("Tempo", "140")
    tsig, _ = _param("TimeSignature", "201")
    tracks = "".join([
        _track("GroupTrack", 10, "DRUMS", -1),
        _track("MidiTrack", 11, "KICK", 10, '<DrumGroupDevice Id="0"><On><Manual Value="true" /></On><Branches /></DrumGroupDevice>',
               _midiclip(0, 64, 128, "kick 4x4", kick_notes) + _midiclip(1, 160, 224, "kick 4x4", kick_notes), out="AudioOut/GroupTrack"),
        _track("MidiTrack", 12, "HATS", 10, '<OriginalSimpler Id="0"><On><Manual Value="true" /></On></OriginalSimpler>',
               _midiclip(0, 32, 128, "hats", hat_notes), out="AudioOut/GroupTrack"),
        _track("GroupTrack", 13, "BASS GROUP", -1, comp),
        _track("MidiTrack", 14, "RUMBLE", 13, f'<Operator Id="0"><On><Manual Value="true" /></On>{op_on}</Operator><Reverb Id="1"><On><Manual Value="true" /></On></Reverb><Eq8 Id="2"><On><Manual Value="true" /></On></Eq8>',
               _midiclip(0, 64, 128, "rumble", bass_notes), out="AudioOut/GroupTrack"),
        _track("MidiTrack", 15, "PAD", -1, f'<InstrumentVector Id="0"><On><Manual Value="true" /></On></InstrumentVector><AutoFilter Id="1"><On><Manual Value="true" /></On>{cutoff}</AutoFilter>',
               _midiclip(0, 64, 128, "pad", pad_notes), pad_env),
        _track("AudioTrack", 16, "TEXTURE", -1, "",
               '<AudioClip Id="0" Time="0"><CurrentStart Value="0" /><CurrentEnd Value="64" /><Loop><LoopStart Value="0" /><LoopEnd Value="64" /><StartRelative Value="0" /><LoopOn Value="false" /></Loop>'
               '<Name Value="texture loop" /><SampleRef><FileRef><RelativePathType Value="3" /><RelativePath Value="Samples/Recorded/texture_loop.wav" /><Path Value="/Users/producer/Music/Demo Project/Samples/Recorded/texture_loop.wav" /></FileRef></SampleRef></AudioClip>'),
        _track("MidiTrack", 17, "MYSTERY SYNTH", -1, '<PluginDevice Id="0"><On><Manual Value="true" /></On><PluginDesc><VstPluginInfo><PlugName Value="UnknownVendor Mono" /></VstPluginInfo></PluginDesc></PluginDevice>'),
        _track("ReturnTrack", 18, "A-Reverb", -1, '<Reverb Id="0"><On><Manual Value="true" /></On></Reverb>'),
        _track("ReturnTrack", 19, "B-Delay", -1, '<Delay Id="0"><On><Manual Value="true" /></On></Delay>'),
    ])
    tempo_env = (f'<AutomationEnvelope Id="0"><EnvelopeTarget><PointeeId Value="{tempo_id}" /></EnvelopeTarget><Automation><Events>'
                 f'<FloatEvent Id="1" Time="-63072000" Value="140" /></Events></Automation></AutomationEnvelope>')
    master = (f'<MasterTrack><LomId Value="0" /><Name><EffectiveName Value="Master" /><UserName Value="" /></Name>'
              f'<AutomationEnvelopes><Envelopes>{tempo_env}</Envelopes></AutomationEnvelopes>'
              f'<DeviceChain><AudioOutputRouting><Target Value="AudioOut/External/S0" /></AudioOutputRouting>'
              f'<Mixer><Sends />{tempo}{tsig}</Mixer><DeviceChain><Devices><Limiter Id="0"><On><Manual Value="true" /></On></Limiter></Devices></DeviceChain></DeviceChain></MasterTrack>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Ableton MajorVersion="5" MinorVersion="11.0_433" SchemaChangeCount="3" Creator="Ableton Live 11.3.4" Revision="parametric-fixture">\n'
            f'<LiveSet>\n<NextPointeeId Value="{_aid[0] + 1}" />\n<Tracks>\n{tracks}\n</Tracks>\n{master}\n'
            '<Transport><LoopOn Value="true" /><LoopStart Value="64" /><LoopLength Value="32" /></Transport>\n'
            '<Locators><Locators><Locator Id="0"><Time Value="0" /><Name Value="Intro" /></Locator><Locator Id="1"><Time Value="64" /><Name Value="Main" /></Locator></Locators></Locators>\n'
            '<Scenes><Scene Id="0"><Name Value="Scene 1" /></Scene><Scene Id="1"><Name Value="Peak" /></Scene></Scenes>\n'
            '<ParametricUnknownFutureBlock Flavor="opaque" Level="7"><Opaque Data="preserve-me" /></ParametricUnknownFutureBlock>\n'
            '</LiveSet>\n</Ableton>\n').replace("><", ">\n<")


def build_demo_als():
    return gzip.compress(build_demo_xml().encode("utf-8"), mtime=0)
