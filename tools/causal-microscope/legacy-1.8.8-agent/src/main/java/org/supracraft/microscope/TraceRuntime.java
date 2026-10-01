package org.supracraft.microscope;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.lang.reflect.Field;
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
    private static final ArrayBlockingQueue<String> QUEUE=
        new ArrayBlockingQueue<String>(8192);
    private static volatile BufferedWriter writer;
    private static volatile Thread writerThread;
    private static volatile String adapter="unknown";

    private TraceRuntime() {}

    public static synchronized void start(String adapterId,String output) {
        if (RUNNING.get()) return;
        try {
            adapter=adapterId;
            File file=new File(output).getAbsoluteFile();
            File parent=file.getParentFile();
            if (parent!=null) parent.mkdirs();
            writer=new BufferedWriter(new OutputStreamWriter(
                new FileOutputStream(file),StandardCharsets.UTF_8),65536);
            RUNNING.set(true);
            writerThread=new Thread(new Runnable() {
                @Override public void run() { writerLoop(); }
            },"supracraft-causal-trace-writer");
            writerThread.setDaemon(true);
            writerThread.start();
            emit("trace_start",
                "{\"adapter\":\""+escape(adapter)+
                "\",\"trace_schema\":\"supracraft-causal-trace/1\"}");
        } catch (Exception exc) {
            System.err.println("SupraCraft causal microscope trace start failed: "+
                exc.getClass().getName());
            Runtime.getRuntime().halt(73);
        }
    }

    public static void tickStart() {
        TICK.incrementAndGet();
        emit("tick_start","{}");
    }

    public static void tickEnd() {
        emit("tick_end","{}");
    }

    public static void event(String eventType) {
        emit(eventType,"{}");
    }

    public static void eventPos(String eventType,Object pos) {
        int[] xyz=position(pos);
        emit(eventType,"{\"x\":"+xyz[0]+",\"y\":"+xyz[1]+
            ",\"z\":"+xyz[2]+"}");
    }

    public static void eventInt(String eventType,int value) {
        emit(eventType,"{\"value\":"+value+"}");
    }

    public static void commandTriggerStart(Object logic) {
        try {
            String command=String.valueOf(readField(logic,"e"));
            String verb=commandVerb(command);
            Object pos=invokeNoArg(logic,"c");
            int[] xyz=position(pos);
            emit("command_trigger_start",
                "{\"x\":"+xyz[0]+",\"y\":"+xyz[1]+",\"z\":"+xyz[2]+
                ",\"command_verb\":\""+escape(verb)+
                "\",\"command_sha256\":\""+sha256(command)+"\"}");
        } catch (Exception exc) {
            fatalBinding("command_trigger_runtime",1,0);
        }
    }

    public static void commandTriggerEnd(Object logic) {
        try {
            int success=((Number)readField(logic,"b")).intValue();
            Object pos=invokeNoArg(logic,"c");
            int[] xyz=position(pos);
            emit("command_trigger_end",
                "{\"x\":"+xyz[0]+",\"y\":"+xyz[1]+",\"z\":"+xyz[2]+
                ",\"success_count\":"+success+"}");
        } catch (Exception exc) {
            fatalBinding("command_trigger_result_runtime",1,0);
        }
    }

    public static void packetSend(Object packet) {
        if (packet==null || !"fy".equals(packet.getClass().getName())) return;
        try {
            ClassLoader loader=packet.getClass().getClassLoader();
            Object component=invokeNoArg(packet,"a");
            Class<?> componentType=Class.forName("eu",false,loader);
            Class<?> serializer=Class.forName("eu$a",false,loader);
            Method serialize=serializer.getMethod("a",componentType);
            serialize.setAccessible(true);
            String wire=(String)serialize.invoke(null,component);
            int position=((Number)invokeNoArg(packet,"c")).intValue() & 0xff;
            emit("packet_send",
                "{\"packet_class\":\"chat\",\"packet_position\":"+position+
                ",\"payload_sha256\":\""+sha256(wire)+
                "\",\"runtime_class\":\"fy\"}");
        } catch (Exception exc) {
            fatalBinding("chat_packet_runtime",1,0);
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
        emit("trace_end","{\"dropped_events\":"+DROPPED.get()+"}");
        RUNNING.set(false);
        Thread thread=writerThread;
        if (thread!=null) {
            try { thread.join(5000L); }
            catch (InterruptedException exc) { Thread.currentThread().interrupt(); }
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
                ((Number)invokeNoArg(pos,"n")).intValue(),
                ((Number)invokeNoArg(pos,"o")).intValue(),
                ((Number)invokeNoArg(pos,"p")).intValue()
            };
        } catch (Exception exc) {
            fatalBinding("block_pos_runtime",3,0);
            return new int[]{0,0,0};
        }
    }

    private static Object invokeNoArg(Object target,String name)
            throws Exception {
        Method method=target.getClass().getMethod(name);
        method.setAccessible(true);
        return method.invoke(target);
    }

    private static Object readField(Object target,String name) throws Exception {
        Class<?> type=target.getClass();
        while (type!=null) {
            try {
                Field field=type.getDeclaredField(name);
                field.setAccessible(true);
                return field.get(target);
            } catch (NoSuchFieldException missing) {
                type=type.getSuperclass();
            }
        }
        throw new NoSuchFieldException(name);
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
