package org.supracraft.microscope;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

public final class TraceRuntime {
    private static final AtomicLong SEQ=new AtomicLong();
    private static final AtomicLong DROPPED=new AtomicLong();
    private static final AtomicLong TICK=new AtomicLong(-1);
    private static final AtomicBoolean RUNNING=new AtomicBoolean(false);
    private static final AtomicBoolean CAPTURE=new AtomicBoolean(true);
    private static final ArrayBlockingQueue<String> QUEUE=
        new ArrayBlockingQueue<String>(16384);
    private static volatile BufferedWriter writer;
    private static volatile Thread writerThread;
    private static volatile Thread gateThread;
    private static volatile String adapter="unknown";

    private TraceRuntime() {}

    public static synchronized void start(
            String adapterId,String output,String gate) {
        if (RUNNING.get()) return;
        try {
            adapter=adapterId;
            File file=new File(output).getAbsoluteFile();
            File parent=file.getParentFile();
            if (parent!=null) parent.mkdirs();
            writer=new BufferedWriter(new OutputStreamWriter(
                new FileOutputStream(file),StandardCharsets.UTF_8),65536);
            CAPTURE.set(gate==null || gate.isEmpty());
            RUNNING.set(true);
            writerThread=new Thread(new Runnable() {
                @Override public void run() { writerLoop(); }
            },"supracraft-causal-trace-writer");
            writerThread.setDaemon(true);
            writerThread.start();
            emitAlways("trace_start",
                "{\"adapter\":\""+escape(adapter)+
                "\",\"trace_schema\":\"supracraft-causal-trace/1\"}");
            if (!CAPTURE.get()) {
                startGateThread(new File(gate).getAbsoluteFile());
            }
        } catch (Exception exc) {
            System.err.println(
                "SupraCraft causal microscope trace start failed: "+
                exc.getClass().getName());
            Runtime.getRuntime().halt(73);
        }
    }

    private static void startGateThread(final File gate) {
        gateThread=new Thread(new Runnable() {
            @Override public void run() {
                while (RUNNING.get() && !CAPTURE.get()) {
                    if (gate.isFile()) {
                        CAPTURE.set(true);
                        return;
                    }
                    try { Thread.sleep(25L); }
                    catch (InterruptedException exc) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
            }
        },"supracraft-causal-capture-gate");
        gateThread.setDaemon(true);
        gateThread.start();
    }

    public static void tickStart() {
        TICK.incrementAndGet();
        if (CAPTURE.get()) emit("tick_start","{}");
    }

    public static void tickEnd() {
        if (CAPTURE.get()) emit("tick_end","{}");
    }

    public static void eventPos(String eventType,Object pos) {
        if (!CAPTURE.get()) return;
        int[] xyz=position(pos);
        emit(eventType,"{\"x\":"+xyz[0]+",\"y\":"+xyz[1]+
            ",\"z\":"+xyz[2]+"}");
    }

    public static void eventIntPos(int value,String eventType,Object pos) {
        if (!CAPTURE.get()) return;
        int[] xyz=position(pos);
        emit(eventType,"{\"x\":"+xyz[0]+",\"y\":"+xyz[1]+
            ",\"z\":"+xyz[2]+",\"value\":"+value+"}");
    }

    public static void commandTriggerStart(Object pos,Object logic) {
        if (!CAPTURE.get()) return;
        try {
            String command=String.valueOf(invokeNoArg(logic,"getCommand"));
            int[] xyz=position(pos);
            emit("command_trigger_start",
                "{\"x\":"+xyz[0]+",\"y\":"+xyz[1]+",\"z\":"+xyz[2]+
                ",\"command_verb\":\""+escape(commandVerb(command))+
                "\",\"command_sha256\":\""+sha256(command)+"\"}");
        } catch (Exception exc) {
            fatalBinding("modern_command_trigger_runtime",1,0);
        }
    }

    public static void commandTriggerEnd(Object pos) {
        if (!CAPTURE.get()) return;
        int[] xyz=position(pos);
        emit("command_trigger_end",
            "{\"x\":"+xyz[0]+",\"y\":"+xyz[1]+",\"z\":"+xyz[2]+"}");
    }

    public static void commandDispatch(String kind,String command) {
        if (!CAPTURE.get()) return;
        try {
            emit("command_dispatch",
                "{\"dispatch_kind\":\""+escape(kind)+
                "\",\"command_verb\":\""+escape(commandVerb(command))+
                "\",\"command_sha256\":\""+sha256(command)+"\"}");
        } catch (Exception exc) {
            fatalBinding("modern_command_dispatch_runtime",1,0);
        }
    }

    public static void fatalBinding(String binding,int expected,int actual) {
        System.err.println(
            "SupraCraft causal microscope fail-closed binding: "+binding+
            " expected="+expected+" actual="+actual);
        System.err.flush();
        Runtime.getRuntime().halt(73);
    }

    public static synchronized void close() {
        if (!RUNNING.get()) return;
        emitAlways("trace_end","{\"dropped_events\":"+DROPPED.get()+"}");
        RUNNING.set(false);
        Thread thread=writerThread;
        if (thread!=null) {
            try { thread.join(5000L); }
            catch (InterruptedException exc) {
                Thread.currentThread().interrupt();
            }
        }
        try {
            if (writer!=null) {
                writer.flush();
                writer.close();
            }
        } catch (Exception ignored) {}
        writer=null;
    }

    private static void emit(String eventType,String dataJson) {
        if (!RUNNING.get() || !CAPTURE.get()) return;
        emitAlways(eventType,dataJson);
    }

    private static void emitAlways(String eventType,String dataJson) {
        if (!RUNNING.get()) return;
        long seq=SEQ.incrementAndGet();
        String row="{\"schema\":\"supracraft-causal-event/1\""+
            ",\"seq\":"+seq+
            ",\"event_type\":\""+escape(eventType)+"\""+
            ",\"monotonic_ns\":"+System.nanoTime()+
            ",\"thread_id\":"+Thread.currentThread().getId()+
            ",\"tick\":"+TICK.get()+
            ",\"data\":"+dataJson+"}";
        if (!QUEUE.offer(row)) DROPPED.incrementAndGet();
    }

    private static void writerLoop() {
        try {
            while (RUNNING.get() || !QUEUE.isEmpty()) {
                String row=QUEUE.poll(100L,TimeUnit.MILLISECONDS);
                if (row==null) continue;
                writer.write(row);
                writer.newLine();
            }
        } catch (Exception exc) {
            DROPPED.incrementAndGet();
            RUNNING.set(false);
        }
    }

    private static int[] position(Object pos) {
        try {
            return new int[]{
                ((Number)invokeNoArg(pos,"getX")).intValue(),
                ((Number)invokeNoArg(pos,"getY")).intValue(),
                ((Number)invokeNoArg(pos,"getZ")).intValue()
            };
        } catch (Exception exc) {
            fatalBinding("modern_block_pos_runtime",3,0);
            return new int[]{0,0,0};
        }
    }

    private static Object invokeNoArg(Object target,String name)
            throws Exception {
        Class<?> type=target.getClass();
        while (type!=null) {
            try {
                Method method=type.getDeclaredMethod(name);
                method.setAccessible(true);
                return method.invoke(target);
            } catch (NoSuchMethodException missing) {
                type=type.getSuperclass();
            }
        }
        throw new NoSuchMethodException(name);
    }

    private static String commandVerb(String command) {
        String s=command==null ? "" : command.trim();
        if (s.startsWith("/")) s=s.substring(1);
        int space=s.indexOf(' ');
        String verb=(space<0 ? s : s.substring(0,space))
            .toLowerCase(Locale.ROOT);
        if (!verb.matches("[a-z0-9_:-]+")) return "unknown";
        return verb.length()>64 ? verb.substring(0,64) : verb;
    }

    private static String sha256(String value) throws Exception {
        MessageDigest md=MessageDigest.getInstance("SHA-256");
        byte[] digest=md.digest(value.getBytes(StandardCharsets.UTF_8));
        StringBuilder out=new StringBuilder(64);
        for (byte b:digest) out.append(String.format("%02x",b & 0xff));
        return out.toString();
    }

    private static String escape(String text) {
        return text.replace("\\","\\\\").replace("\"","\\\"");
    }
}
