from vsiddump import reg_processor


def test_process_data():
    processor = reg_processor()
    assert b"1 0 3 15\n6 0 5 6\n" == processor.process("1 3 31\n1 3 15\n4 5 6\n")
